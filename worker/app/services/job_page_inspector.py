import os
import re
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
    """Render an allow-listed Greenhouse job, optionally open its application form, and capture screenshots.

    Screenshots are returned to the caller for one multimodal model request. They are not
    written to disk or retained in the browser session.
    """
    board_token, job_id = parse_greenhouse_job_url(url)
    if not _enabled():
        return {
            "status": "disabled",
            "screenshots": [],
            "page_title": None,
            "page_headings": [],
            "rendered_text": "",
            "note": "Visual page inspection is disabled by configuration.",
        }

    playwright = None
    browser = None
    context = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=1,
            locale="en-US",
            accept_downloads=False,
            service_workers="block",
        )
        page = await context.new_page()
        page.set_default_navigation_timeout(45000)
        page.set_default_timeout(8000)

        allowed_application_url = None

        def is_allowed_application_url(candidate: str) -> bool:
            try:
                from urllib.parse import urlparse
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
                try:
                    redirected_board, redirected_job_id = parse_greenhouse_job_url(request.url)
                except Exception:
                    await route.abort()
                    return
                is_job_page = redirected_board == board_token and redirected_job_id == job_id
                is_apply_page = is_allowed_application_url(request.url)
                if not is_job_page and not is_apply_page:
                    await route.abort()
                    return
            await route.continue_()

        # Validate redirects before Chromium is allowed to fetch the new top-level page.
        await page.route("**/*", guard_main_frame_navigation)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(900)

        # Do not follow a redirect to a different host, board, or job.
        if not (is_allowed_application_url(page.url)):
            final_board_token, final_job_id = parse_greenhouse_job_url(page.url)
            if final_board_token != board_token or final_job_id != job_id:
                raise ValueError("The rendered page redirected to a different Greenhouse job.")

        application_form_opened = is_allowed_application_url(page.url)
        apply_action = "already_on_application_form" if application_form_opened else "not_attempted"
        if navigate_to_apply and not application_form_opened:
            # Only click an Apply affordance whose target is a same-board, same-job /apply route.
            candidates = page.locator("a[href], button, [role=button]").filter(has_text=re.compile(r"apply", re.I))
            for index in range(min(await candidates.count(), 12)):
                candidate = candidates.nth(index)
                try:
                    href = await candidate.get_attribute("href")
                    if href:
                        from urllib.parse import urljoin
                        target = urljoin(page.url, href)
                        if not is_allowed_application_url(target):
                            continue
                    await candidate.click(timeout=3500)
                    await page.wait_for_timeout(700)
                    if is_allowed_application_url(page.url):
                        application_form_opened = True
                        apply_action = "clicked_apply"
                        break
                    # Inline forms may reveal without navigation. Detect visible form controls.
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
            " ".join(value.split())[:180]
            for value in headings
            if value and value.strip()
        ))[:30]

        try:
            rendered_text = await page.locator("body").inner_text(timeout=8000)
        except Exception:
            rendered_text = ""
        rendered_text = rendered_text[:12000]

        # Extract only visible control metadata; never collect entered values.
        form_controls = await page.locator("input:not([type=hidden]), textarea, select, [role=checkbox], [role=radio]").evaluate_all("""els => els.filter(e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)).slice(0,100).map(e => ({ tag:e.tagName.toLowerCase(), type:e.getAttribute("type") || (e.tagName.toLowerCase()==="select" ? "select" : e.tagName.toLowerCase()), name:e.getAttribute("name"), id:e.id || null, label:(e.labels && Array.from(e.labels).map(l=>l.innerText).join(" ")) || e.getAttribute("aria-label") || e.getAttribute("placeholder") || null, required:!!e.required || e.getAttribute("aria-required")==="true", options:e.tagName.toLowerCase()==="select" ? Array.from(e.options).map(o=>o.text).slice(0,30) : [], visible:true }))""")

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
                type="jpeg",
                quality=72,
                full_page=False,
                animations="disabled",
                timeout=15000,
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
            "page_headings": page_headings,
            "rendered_text": rendered_text,
            "form_controls": form_controls,
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
