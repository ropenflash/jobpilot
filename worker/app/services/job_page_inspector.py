import os
from playwright.async_api import async_playwright

from app.services.greenhouse import parse_greenhouse_job_url


VIEWPORT = {"width": 1440, "height": 1000}
MAX_SCREENSHOTS = 5


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


async def inspect_greenhouse_job_page(url: str) -> dict:
    """Render an allow-listed Greenhouse job and capture in-memory viewport screenshots.

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

        async def guard_main_frame_navigation(route):
            request = route.request
            if request.is_navigation_request() and request.frame == page.main_frame:
                try:
                    redirected_board, redirected_job_id = parse_greenhouse_job_url(request.url)
                except Exception:
                    await route.abort()
                    return
                if redirected_board != board_token or redirected_job_id != job_id:
                    await route.abort()
                    return
            await route.continue_()

        # Validate redirects before Chromium is allowed to fetch the new top-level page.
        await page.route("**/*", guard_main_frame_navigation)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(900)

        # Do not follow a redirect to a different host or a different job.
        final_board_token, final_job_id = parse_greenhouse_job_url(page.url)
        if final_board_token != board_token or final_job_id != job_id:
            raise ValueError("The rendered page redirected to a different Greenhouse job.")

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
