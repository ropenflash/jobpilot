import asyncio
import base64
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright


ALLOWED_GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
FIELD_SELECTOR = "input:not([type='hidden']), textarea, select"
CHALLENGE_TERMS = ("verify you are human", "unusual traffic", "captcha", "robot check", "security check")


class ApplicationAutomationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_greenhouse_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_GREENHOUSE_HOSTS:
        raise ApplicationAutomationError("Only HTTPS Greenhouse job postings are supported.")
    if not re.match(r"^/[^/]+/jobs/\d+(?:/.*)?$", parsed.path):
        raise ApplicationAutomationError("Use a public Greenhouse job-posting URL, not an arbitrary page.")
    return value


def _classify_field(label: str, name: str, input_type: str) -> str:
    text = f"{label} {name}".lower().replace("_", " ").replace("-", " ")
    if any(term in text for term in ("race", "ethnicity", "gender", "veteran", "disability",
                                     "sexual orientation", "pronoun", "date of birth",
                                     "citizenship", "work authorization", "sponsorship")):
        return "sensitive_or_eligibility"
    if input_type == "file" and any(term in text for term in ("resume", "cv")):
        return "resume"
    if "full name" in text or text.strip() in {"name", "candidate name"}:
        return "full_name"
    if "first name" in text or text.strip() in {"first", "firstname", "fname"}:
        return "first_name"
    if "last name" in text or text.strip() in {"last", "lastname", "lname", "surname"}:
        return "last_name"
    if "email" in text:
        return "email"
    if "phone" in text or "mobile" in text or "telephone" in text:
        return "phone"
    if "linkedin" in text:
        return "linkedin"
    if "github" in text:
        return "github"
    if "portfolio" in text or "website" in text or "personal site" in text:
        return "website"
    return "manual"


@dataclass
class BrowserSession:
    session_id: str
    playwright: object
    browser: object
    context: object
    page: object
    frame: object
    upload_path: Path
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    status: str = "BROWSER_OPEN"
    application_url: str = ""
    fields: list[dict] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)
    message: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ApplicationSessionManager:
    def __init__(self):
        self.sessions: dict[str, BrowserSession] = {}
        self.ttl_seconds = int(os.getenv("JOBPILOT_APPLICATION_SESSION_TTL_SECONDS", "2700"))
        self.headless = os.getenv("JOBPILOT_BROWSER_HEADLESS", "false").lower() in {"1", "true", "yes"}

    async def prepare(self, application_id: str, job_url: str, career_profile: dict,
                      resume_pdf_base64: str) -> dict:
        _validate_greenhouse_url(job_url)
        await self._expire_stale_sessions()
        try:
            pdf_bytes = base64.b64decode(resume_pdf_base64, validate=True)
        except Exception as exc:
            raise ApplicationAutomationError("The tailored PDF payload is invalid.") from exc
        if not pdf_bytes.startswith(b"%PDF") or len(pdf_bytes) > 12 * 1024 * 1024:
            raise ApplicationAutomationError("The tailored resume must be a valid PDF under 12 MB.")

        upload_dir = Path(tempfile.gettempdir()) / "jobpilot-applications"
        upload_dir.mkdir(parents=True, exist_ok=True)
        upload_path = upload_dir / f"{application_id}.pdf"
        upload_path.write_bytes(pdf_bytes)

        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.launch(headless=self.headless)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            page.set_default_timeout(9000)
            await page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(1800)
            if urlparse(page.url).hostname not in ALLOWED_GREENHOUSE_HOSTS:
                raise ApplicationAutomationError("Greenhouse redirected outside the supported Greenhouse hosts.")

            frame = await self._find_application_frame(page)
            if frame is None:
                await self._click_apply(page)
                await page.wait_for_timeout(1800)
                frame = await self._find_application_frame(page)
            if frame is None:
                if await self._has_challenge(page):
                    frame = page.main_frame
                else:
                    raise ApplicationAutomationError(
                        "The Greenhouse application form was not detected. Check that the job is still active and publicly available."
                    )

            session = BrowserSession(
                session_id=application_id,
                playwright=playwright,
                browser=browser,
                context=context,
                page=page,
                frame=frame,
                upload_path=upload_path,
                application_url=page.url,
            )
            self.sessions[application_id] = session
            session.fields = await self._snapshot_fields(frame)
            await self._autofill(session, career_profile)
            session.fields = await self._snapshot_fields(frame)
            session.missing_required_fields = self._missing_required(session.fields)
            session.status = "NEEDS_USER_INPUT" if session.missing_required_fields else "READY_FOR_REVIEW"
            if await self._has_challenge(page):
                session.status = "NEEDS_USER_INPUT"
                session.message = "A verification or bot-check prompt is visible. Complete it manually in Chromium."
            elif session.missing_required_fields:
                session.message = "Complete the remaining required fields in the visible Chromium window, then refresh this review."
            else:
                session.message = "Contact details and tailored resume are filled. Review the complete form in Chromium before submitting."
            return self._serialize(session)
        except Exception:
            try:
                await playwright.stop()
            except Exception:
                pass
            try:
                upload_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    async def get(self, session_id: str) -> dict:
        session = self._get_session(session_id)
        async with session.lock:
            await self._touch(session)
            if session.status in {"SUBMITTED", "SUBMISSION_UNKNOWN", "SUBMITTING"}:
                raise ApplicationAutomationError(
                    "A submission has already been attempted for this session. Check Greenhouse and your email before taking any further action."
                )
            frame = await self._find_application_frame(session.page)
            if frame is None:
                session.status = "NEEDS_USER_INPUT"
                session.message = "The application form is not available. Review the visible browser before submitting."
                return self._serialize(session)
            session.frame = frame
            session.fields = await self._snapshot_fields(session.frame)
            session.missing_required_fields = self._missing_required(session.fields)
            return self._serialize(session)

    async def refresh(self, session_id: str) -> dict:
        session = self._get_session(session_id)
        async with session.lock:
            await self._touch(session)
            if session.status in {"SUBMITTED", "SUBMISSION_UNKNOWN", "SUBMITTING"}:
                return self._serialize(session)
            frame = await self._find_application_frame(session.page)
            challenge = await self._has_challenge(session.page)
            if frame is not None:
                session.frame = frame
            elif challenge:
                session.frame = session.page.main_frame
            else:
                session.status = "NEEDS_USER_INPUT"
                session.message = "The application form is not currently available in the browser. Finish any page prompt and refresh again."
                return self._serialize(session)
            session.fields = await self._snapshot_fields(session.frame)
            session.missing_required_fields = self._missing_required(session.fields)
            if challenge:
                session.status = "NEEDS_USER_INPUT"
                session.message = "Complete the verification prompt manually in Chromium."
            elif session.missing_required_fields:
                session.status = "NEEDS_USER_INPUT"
                session.message = "Some required fields still need attention in the browser."
            else:
                session.status = "READY_FOR_REVIEW"
                session.message = "All required fields appear complete. Review every answer in Chromium before submitting."
            return self._serialize(session)

    async def submit(self, session_id: str, confirm_submit: bool) -> dict:
        if confirm_submit is not True:
            raise ApplicationAutomationError("Explicit user confirmation is required before submission.")
        session = self._get_session(session_id)
        async with session.lock:
            await self._touch(session)
            session.fields = await self._snapshot_fields(session.frame)
            session.missing_required_fields = self._missing_required(session.fields)
            if session.missing_required_fields:
                session.status = "NEEDS_USER_INPUT"
                session.message = "Submission blocked because required fields are still empty."
                return self._serialize(session)
            if await self._has_challenge(session.page):
                session.status = "NEEDS_USER_INPUT"
                session.message = "Submission blocked by a verification prompt. Complete it manually."
                return self._serialize(session)

            submit_button = await self._find_submit_button(session.frame)
            if submit_button is None:
                session.status = "NEEDS_USER_INPUT"
                session.message = "Could not identify a safe Submit Application button. Submit manually in Chromium."
                return self._serialize(session)

            session.status = "SUBMITTING"
            session.message = "Submitting after explicit confirmation."
            try:
                await submit_button.click()
                await session.page.wait_for_timeout(3500)
                page_text = (await session.page.locator("body").inner_text()).lower()
                success_terms = ("application submitted", "thank you for applying",
                                 "thanks for applying", "application has been received",
                                 "your application was received")
                if any(term in page_text for term in success_terms):
                    session.status = "SUBMITTED"
                    session.message = "Greenhouse displayed an application-received confirmation."
                else:
                    session.status = "SUBMISSION_UNKNOWN"
                    session.message = (
                        "The submit action was triggered, but JobPilot could not verify a confirmation. "
                        "Check the open browser and your email before taking any further action; do not retry blindly."
                    )
            except Exception:
                session.status = "SUBMISSION_UNKNOWN"
                session.message = (
                    "The browser reported an error after the submit action may have started. "
                    "Check Greenhouse manually before retrying."
                )
            refreshed_frame = await self._find_application_frame(session.page)
            if refreshed_frame is not None:
                session.frame = refreshed_frame
                session.fields = await self._snapshot_fields(session.frame)
                session.missing_required_fields = self._missing_required(session.fields)
            else:
                session.fields = []
                session.missing_required_fields = []
            return self._serialize(session)

    async def cancel(self, session_id: str) -> dict:
        session = self._get_session(session_id)
        async with session.lock:
            session.status = "CANCELLED"
            session.message = "Application browser session closed without submitting."
            result = self._serialize(session)
            await self._close_session(session)
            self.sessions.pop(session_id, None)
            return result

    async def _find_application_frame(self, page):
        frames = list(page.frames)
        for frame in frames:
            try:
                if await frame.locator("form").count() and await frame.locator(FIELD_SELECTOR).count():
                    return frame
            except Exception:
                continue
        for frame in frames:
            try:
                if await frame.locator(FIELD_SELECTOR).count() >= 2:
                    return frame
            except Exception:
                continue
        return None

    async def _click_apply(self, page):
        for kind in ("link", "button"):
            try:
                locator = page.get_by_role(kind, name=re.compile(r"^\s*apply(?: now)?\s*$", re.I))
                count = await locator.count()
                for index in range(min(count, 3)):
                    candidate = locator.nth(index)
                    if await candidate.is_visible() and await candidate.is_enabled():
                        await candidate.click()
                        await page.wait_for_timeout(700)
                        return
            except Exception:
                continue

    async def _snapshot_fields(self, frame) -> list[dict]:
        rows = await frame.locator(FIELD_SELECTOR).evaluate_all("""elements => elements.map((el, index) => {
          const type = (el.getAttribute('type') || el.tagName.toLowerCase()).toLowerCase();
          const labels = el.labels ? Array.from(el.labels).map(x => x.innerText).filter(Boolean) : [];
          const labelledBy = el.getAttribute('aria-labelledby');
          const ariaText = labelledBy ? labelledBy.split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ') : '';
          const label = (labels.join(' ') || el.getAttribute('aria-label') || ariaText ||
                         el.getAttribute('placeholder') || el.getAttribute('name') || el.id || 'Unlabelled field').trim();
          const required = Boolean(el.required || el.getAttribute('aria-required') === 'true');
          let filled = false;
          if (type === 'file') filled = Boolean(el.files && el.files.length);
          else if (type === 'checkbox' || type === 'radio') filled = Boolean(el.checked);
          else filled = String(el.value || '').trim().length > 0;
          const options = el.tagName.toLowerCase() === 'select'
            ? Array.from(el.options).filter(o => o.value).map(o => o.textContent.trim()).slice(0, 30) : [];
          return { index, name: el.getAttribute('name') || '', id: el.id || '',
                   label: label.slice(0, 180), type, required, filled, options };
        })""")
        seen_radio_groups = {}
        fields = []
        for item in rows:
            if item["type"] == "radio":
                group = item["name"] or item["label"]
                if group in seen_radio_groups:
                    seen_radio_groups[group]["filled"] = seen_radio_groups[group]["filled"] or item["filled"]
                    continue
                seen_radio_groups[group] = item
            item["classification"] = _classify_field(item["label"], item["name"], item["type"])
            fields.append(item)
        return fields

    def _profile_values(self, profile: dict) -> dict:
        full_name = str(profile.get("full_name") or "").strip()
        parts = full_name.split()
        return {
            "full_name": full_name,
            "first_name": parts[0] if parts else "",
            "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
            "email": str(profile.get("email") or "").strip(),
            "phone": str(profile.get("phone") or "").strip(),
            "linkedin": str(profile.get("linkedin_url") or profile.get("linkedin") or "").strip(),
            "github": str(profile.get("github_url") or profile.get("github") or "").strip(),
            "website": str(profile.get("website") or profile.get("portfolio_url") or "").strip(),
        }

    async def _autofill(self, session: BrowserSession, career_profile: dict):
        values = self._profile_values(career_profile)
        for item in session.fields:
            classification = item["classification"]
            if item["filled"] or item["type"] in {"file", "checkbox", "radio"}:
                continue
            value = values.get(classification, "")
            if value:
                try:
                    await session.frame.locator(FIELD_SELECTOR).nth(item["index"]).fill(value)
                except Exception:
                    continue

        file_fields = [item for item in session.fields
                       if item["type"] == "file" and item["classification"] == "resume"]
        if len(file_fields) == 1:
            try:
                await session.frame.locator(FIELD_SELECTOR).nth(file_fields[0]["index"]).set_input_files(
                    str(session.upload_path)
                )
            except Exception:
                session.message = "The resume upload control needs manual attention in Chromium."

    def _missing_required(self, fields: list[dict]) -> list[str]:
        missing = []
        for item in fields:
            if item["required"] and not item["filled"]:
                missing.append(item["label"])
        return list(dict.fromkeys(missing))

    async def _find_submit_button(self, frame):
        for pattern in (r"^\s*submit application\s*$", r"^\s*submit\s*$"):
            try:
                locator = frame.get_by_role("button", name=re.compile(pattern, re.I))
                count = await locator.count()
                for index in range(min(count, 3)):
                    candidate = locator.nth(index)
                    if await candidate.is_visible() and await candidate.is_enabled():
                        return candidate
            except Exception:
                continue
        return None

    async def _has_challenge(self, page) -> bool:
        try:
            body = (await page.locator("body").inner_text()).lower()
            return any(term in body for term in CHALLENGE_TERMS)
        except Exception:
            return False

    def _get_session(self, session_id: str) -> BrowserSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise ApplicationAutomationError(
                "The browser session is no longer available. Start a new application session."
            )
        return session

    async def _touch(self, session: BrowserSession):
        if time.monotonic() - session.last_activity > self.ttl_seconds:
            await self._close_session(session)
            self.sessions.pop(session.session_id, None)
            raise ApplicationAutomationError("The browser session expired. Start a new application session.")
        session.last_activity = time.monotonic()

    async def _expire_stale_sessions(self):
        now = time.monotonic()
        for session_id, session in list(self.sessions.items()):
            if now - session.last_activity > self.ttl_seconds:
                await self._close_session(session)
                self.sessions.pop(session_id, None)

    async def _close_session(self, session: BrowserSession):
        try:
            await session.context.close()
        except Exception:
            pass
        try:
            await session.browser.close()
        except Exception:
            pass
        try:
            await session.playwright.stop()
        except Exception:
            pass
        try:
            session.upload_path.unlink(missing_ok=True)
        except Exception:
            pass

    def _serialize(self, session: BrowserSession) -> dict:
        return {
            "session_id": session.session_id,
            "status": session.status,
            "application_url": session.application_url,
            "fields": session.fields,
            "missing_required_fields": session.missing_required_fields,
            "message": session.message,
            "updated_at": _utc_now(),
        }


application_sessions = ApplicationSessionManager()
