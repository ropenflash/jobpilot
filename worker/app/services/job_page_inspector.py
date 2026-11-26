import os
import re
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

from app.services.greenhouse import parse_greenhouse_job_url


VIEWPORT = {"width": 1440, "height": 1000}
MAX_SCREENSHOTS = 5
APPLICATION_PATH = re.compile(r"^/([A-Za-z0-9_-]+)/jobs/([0-9]+)/apply/?$")


def _enabled() -> bool:
    return os.getenv("JOBPILOT_JOB_VISUAL_INSPECTION_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _screenshot_limit() -> int:
    try:
        requested = int(os.getenv("JOBPILOT_JOB_SCREENSHOT_COUNT", "4"))
    except ValueError:
        requested = 4
    return max(1, min(requested, MAX_SCREENSHOTS))


def _screenshot_offsets(content_height: int, viewport_height: int, limit: int) -> list[int]:
    """Choose a small set of overlapping viewport positions that cover the page from top down."""
    max_top = max(0, content_height - viewport_height)
    offsets = [0]
    step = max(1, int(viewport_height * 0.82))
    for index in range(1, limit):
        offset = min(max_top, index * step)
        if offset <= offsets[-1]:
            break
        offsets.append(offset)
        if offset >= max_top:
            break
    return offsets


async def inspect_greenhouse_job_page(url: str, navigate_to_apply: bool = False) -> dict:
    """Read-only rendered-page inspection. Collect evidence; never follow external application links."""
    board_token, job_id = parse_greenhouse_job_url(url)
    if not _enabled():
        return {
            "status": "disabled", "screenshots": [], "page_title": None,
            "page_headings": [], "rendered_text": "", "form_controls": [],
            "links": [], "buttons": [], "instructions": [],
            "note": "Visual page inspection is disabled by configuration.",
        }

    playwright = browser = context = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport=VIEWPORT, device_scale_factor=1, locale="en-US",
            accept_downloads=False, service_workers="block",
        )
        page = await context.new_page()
        # Inspection must remain read-only, even if a page has submit handlers.
        await page.add_init_script("""document.addEventListener("submit", event => { event.preventDefault(); event.stopImmediatePropagation(); }, true);""")
        page.set_default_navigation_timeout(45000)
        page.set_default_timeout(8000)

        def is_allowed_application_url(candidate: str) -> bool:
            try:
                parsed = urlparse(candidate)
                match = APPLICATION_PATH.fullmatch(parsed.path)
                return (
                    parsed.scheme == "https"
                    and parsed.hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io"}
                    and not parsed.username and not parsed.password and parsed.port is None
                    and match is not None
                    and match.group(1) == board_token
                    and int(match.group(2)) == job_id
                )
            except (ValueError, TypeError):
                return False

        async def guard_main_frame_navigation(route):
            request = route.request
            if request.is_navigation_request() and request.frame == page.main_frame:
                is_apply_page = is_allowed_application_url(request.url)
                is_job_page = False
                if not is_apply_page:
                    try:
                        redirected_board, redirected_job_id = parse_greenhouse_job_url(request.url)
                        is_job_page = redirected_board == board_token and redirected_job_id == job_id
                    except Exception:
                        is_job_page = False
                if not is_job_page and not is_apply_page:
                    await route.abort()
                    return
            await route.continue_()

        await page.route("**/*", guard_main_frame_navigation)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(900)

        if not is_allowed_application_url(page.url):
            final_board_token, final_job_id = parse_greenhouse_job_url(page.url)
            if final_board_token != board_token or final_job_id != job_id:
                raise ValueError("The rendered page redirected to a different Greenhouse job.")

        application_form_opened = is_allowed_application_url(page.url)
        apply_action = "already_on_application_form" if application_form_opened else "not_attempted"
        if navigate_to_apply and not application_form_opened:
            candidates = page.locator("a[href], button:not([type=submit]), [role=button]:not([type=submit])").filter(has_text=re.compile(r"apply", re.I))
            for index in range(min(await candidates.count(), 12)):
                candidate = candidates.nth(index)
                try:
                    href = await candidate.get_attribute("href")
                    if href:
                        target = urljoin(page.url, href)
                        if not is_allowed_application_url(target):
                            continue
                    await candidate.click(timeout=3500)
                    await page.wait_for_timeout(700)
                    if is_allowed_application_url(page.url):
                        application_form_opened = True
                        apply_action = "clicked_apply"
                        break
                    visible_controls = await page.locator("input:not([type=hidden]), textarea, select").evaluate_all(
                        "(els) => els.filter(e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)).length"
                    )
                    if visible_controls:
                        application_form_opened = True
                        apply_action = "opened_inline_form"
                        break
                except Exception:
                    continue

        page_title = (await page.title()).strip()[:240] or None
        try:
            headings = await page.locator("h1, h2, h3").all_inner_texts()
        except Exception:
            headings = []
        page_headings = list(dict.fromkeys(
            " ".join(value.split())[:180] for value in headings if value and value.strip()
        ))[:30]
        try:
            rendered_text = await page.locator("body").inner_text(timeout=8000)
        except Exception:
            rendered_text = ""
        rendered_text = rendered_text[:20000]

        form_controls = await page.locator(
            "input:not([type=hidden]), textarea, select, [role=checkbox], [role=radio], "
            "[role=combobox], [aria-haspopup=listbox]"
        ).evaluate_all("""els => els.filter(e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)).slice(0,100).map(e => {
          const labels = e.labels ? Array.from(e.labels).map(l => (l.innerText || l.textContent || '').trim()).filter(Boolean) : [];
          const labelledBy = e.getAttribute('aria-labelledby');
          const ariaLabelled = labelledBy ? labelledBy.split(/\\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ') : '';
          const parent = e.closest('[data-field], .field, .form-field, fieldset, .question') || e.parentElement;
          const context = parent ? (parent.innerText || parent.textContent || '').trim() : '';
          const options = e.tagName.toLowerCase() === 'select' || e.getAttribute('role') === 'combobox'
            ? Array.from(e.options || []).map(o => ({text:(o.textContent || '').trim(), value:o.value, disabled:!!o.disabled})).slice(0,50)
            : [];
          return {
            tag:e.tagName.toLowerCase(),
            type:e.getAttribute('type') || (e.tagName.toLowerCase()==='select' ? 'select' : e.tagName.toLowerCase()),
            name:e.getAttribute('name'), id:e.id || null,
            label:labels.join(' ') || ariaLabelled || e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.getAttribute('name') || e.id || null,
            placeholder:e.getAttribute('placeholder'),
            required:!!e.required || e.getAttribute('aria-required')==='true',
            accept:e.getAttribute('accept'), autocomplete:e.getAttribute('autocomplete'),
            options, context:context.slice(0,500), visible:true
          };
        })""")

        links = await page.locator("a[href]").evaluate_all("""els => els.filter(a => !!(a.offsetWidth || a.offsetHeight || a.getClientRects().length)).slice(0,150).map(a => {
          const parent = a.closest('p, li, section, article, fieldset, .field, .form-field') || a.parentElement;
          return {
            text:(a.innerText || a.textContent || '').trim().slice(0,300),
            href:a.href, target:a.target || null,
            context:(parent ? (parent.innerText || parent.textContent || '') : '').trim().slice(0,700),
            visible:true
          };
        })""")
        buttons = await page.locator("button, [role=button], input[type=submit]").evaluate_all("""els => els.filter(e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)).slice(0,80).map(e => ({
          text:(e.innerText || e.textContent || e.getAttribute('aria-label') || '').trim().slice(0,250),
          type:e.getAttribute('type'), disabled:!!e.disabled,
          context:(e.parentElement ? (e.parentElement.innerText || '').trim() : '').slice(0,400)
        }))""")

        # Short, evidence-derived instruction snippets; the LLM workflow agent will classify these.
        instruction_patterns = re.compile(
            r"(apply (?:through|via|on|at)|complete.{0,100}application|instead.{0,100}(?:apply|application)|"
            r"use the provided link|register your interest|must.{0,100}(?:complete|submit|apply)|"
            r"application.{0,100}(?:required|form|link))", re.I
        )
        instructions = list(dict.fromkeys(
            " ".join(line.split())[:700]
            for line in rendered_text.splitlines()
            if line.strip() and instruction_patterns.search(line)
        ))[:40]

        dimensions = await page.evaluate("""() => ({
          height: Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight || 0),
          viewport: window.innerHeight
        })""")
        offsets = _screenshot_offsets(
            int(dimensions.get("height") or VIEWPORT["height"]),
            int(dimensions.get("viewport") or VIEWPORT["height"]),
            _screenshot_limit(),
        )
        screenshots: list[bytes] = []
        for offset in offsets:
            await page.evaluate("(top) => window.scrollTo(0, top)", offset)
            await page.wait_for_timeout(180)
            screenshot = await page.screenshot(
                type="jpeg", quality=72, full_page=False,
                animations="disabled", timeout=15000,
            )
            if screenshot:
                screenshots.append(screenshot)

        response_status = response.status if response is not None else None
        note = None
        if response_status is not None and response_status >= 400:
            note = f"The rendered page returned HTTP {response_status}; visual observations may be incomplete."
        if not screenshots and not note:
            note = "The browser did not produce any screenshots."

        return {
            "status": "completed" if screenshots else "unavailable",
            "screenshots": screenshots,
            "page_title": page_title,
            "page_url": page.url,
            "page_headings": page_headings,
            "rendered_text": rendered_text,
            "form_controls": form_controls,
            "links": links,
            "buttons": buttons,
            "instructions": instructions,
            "application_form_opened": application_form_opened,
            "apply_action": apply_action,
            "note": note,
        }
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass
