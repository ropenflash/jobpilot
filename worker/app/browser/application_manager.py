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

from app.agents.application_question_reviewer import build_evidence, review_application_questions
from app.agents.application_answer_resolver import (
    _direct_technology_years,
    _inferred_technology_years,
)


ALLOWED_GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
FIELD_SELECTOR = "input:not([type='hidden']), textarea, select, [role='combobox'], [role='checkbox'], [role='radio'], [aria-haspopup='listbox']"
CHALLENGE_TERMS = ("verify you are human", "unusual traffic", "captcha", "robot check", "security check")


class ApplicationAutomationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _match_country_code_option(options: list[dict], phone: str) -> dict | None:
    """Return one unambiguous option matching an international phone prefix."""
    if not phone.strip().startswith("+"):
        return None

    phone_digits = re.sub(r"\D", "", phone)
    matches = []
    for index, option in enumerate(options):
        value = str(option.get("value") or "").strip()
        label = str(option.get("text") or "").strip()

        code_match = re.fullmatch(r"\+?(\d{1,3})", value)
        if code_match is None:
            code_match = re.search(r"\+\s*(\d{1,3})\b", label)
        if code_match is None and re.fullmatch(r"\+?\d{1,3}", label):
            code_match = re.fullmatch(r"\+?(\d{1,3})", label)
        if code_match is None:
            continue

        calling_code = code_match.group(1)
        if phone_digits.startswith(calling_code) and len(phone_digits) > len(calling_code) + 4:
            matches.append({
                **option,
                "index": option.get("index", index),
                "calling_code": calling_code,
            })

    if not matches:
        return None
    longest = max(len(item["calling_code"]) for item in matches)
    best = [item for item in matches if len(item["calling_code"]) == longest]
    return best[0] if len(best) == 1 else None


def _national_number(phone: str, calling_code: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if phone.strip().startswith("+") and digits.startswith(calling_code):
        return digits[len(calling_code):]
    return phone.strip()


def _resume_upload_score(metadata: dict) -> int:
    """Score file inputs without confusing resume uploads with cover-letter fields."""
    label = str(metadata.get("label") or "")
    name = str(metadata.get("name") or "")
    element_id = str(metadata.get("id") or "")
    parent_text = str(metadata.get("parent_text") or "")
    accept = str(metadata.get("accept") or "")
    text = " ".join((label, name, element_id, parent_text)).lower()

    if any(term in text for term in (
        "cover letter", "work sample", "writing sample", "portfolio", "additional document"
    )) and not re.search(r"\b(resume|cv|curriculum vitae)\b", text):
        return -1
    if re.search(r"\b(resume|cv|curriculum vitae)\b", " ".join((label, name, element_id)).lower()):
        return 100
    if any(token in accept.lower() for token in (
        ".pdf", "application/pdf", ".docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )):
        return 20
    return 0


def _validate_greenhouse_url(value: str):
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_GREENHOUSE_HOSTS:
        raise ApplicationAutomationError("Only HTTPS Greenhouse job postings are supported.")
    if not re.match(r"^/[^/]+/jobs/\d+(?:/.*)?$", parsed.path):
        raise ApplicationAutomationError("Use a public Greenhouse job-posting URL, not an arbitrary page.")
    return value


def _classify_field(label: str, name: str, input_type: str) -> str:
    text = f"{label} {name}".lower().replace("_", " ").replace("-", " ")
    compact = re.sub(r"[^a-z0-9]+", " ", text).strip()
    if "unlabelled field" in text or text.strip() == "unlabelled":
        return "unlabelled_field"
    if "expected ctc" in text or "expected compensation" in text or "desired ctc" in text:
        return "expected_ctc"
    if "current ctc" in text or "current compensation" in text or "present ctc" in text:
        return "current_ctc"
    if "official notice period" in text or "notice period" in text:
        return "notice_period"
    if "last working day" in text or "last day of work" in text:
        return "last_working_day"
    if any(term in text for term in ("how soon can you join", "when can you join", "joining availability", "available to join")):
        return "join_availability"
    if "spring" in text and "microservice" in text and any(term in text for term in ("experience", "years")):
        return "years_spring_boot_microservices"
    if "java" in text and any(term in text for term in ("experience", "years")):
        return "years_java"
    if "spring" in text and any(term in text for term in ("experience", "years")):
        return "years_spring_boot"
    if "microservice" in text and any(term in text for term in ("experience", "years")):
        return "years_microservices"
    if "kafka" in text and any(term in text for term in ("experience", "years")):
        return "years_kafka"
    if ("gcp" in compact or "google cloud" in text) and any(term in text for term in ("experience", "years")):
        return "years_gcp"
    if any(term in text for term in (
        "race", "ethnicity", "gender", "veteran", "disability",
        "sexual orientation", "pronoun", "date of birth", "citizenship",
        "work authorization", "work authorisation", "sponsorship",
        "previously employed", "previously been employed", "previous employment", "ever employed",
        "worked for", "eligible to work",
    )):
        return "sensitive_or_eligibility"
    if any(term in text for term in ("country code", "dial code", "phone code", "telephone code", "mobile code")):
        return "phone_country_code"
    if input_type == "file" and any(term in text for term in ("resume", "cv")):
        return "resume"
    if input_type == "checkbox":
        return "checkbox_review"
    if any(term in text for term in (
        "professional software experience", "experience range", "years of experience",
        "total experience", "experience in software",
    )):
        return "experience_range"
    if "country" in text:
        return "country"
    if "city" in text or "location" in text:
        return "city"
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


def _match_experience_range_option(options: list[dict], years: float) -> dict | None:
    """Return an option only when exactly one label unambiguously contains the verified years."""
    matches = []
    for option in options:
        label = str(option.get("text") or "").strip().lower()
        if not label:
            continue
        range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)", label)
        if range_match:
            lower, upper = float(range_match.group(1)), float(range_match.group(2))
            if lower <= years <= upper:
                matches.append(option)
            continue
        plus_match = re.search(r"(\d+(?:\.\d+)?)\s*\+", label)
        if plus_match:
            if years >= float(plus_match.group(1)):
                matches.append(option)
            continue
        less_match = re.search(r"(?:less than|under|below)\s*(\d+(?:\.\d+)?)", label)
        if less_match and years < float(less_match.group(1)):
            matches.append(option)
    return matches[0] if len(matches) == 1 else None

@dataclass
class BrowserSession:
    session_id: str
    playwright: object
    browser: object
    context: object
    page: object
    frame: object
    upload_path: Path
    career_profile: dict = field(default_factory=dict)
    tailored_resume: dict = field(default_factory=dict)
    form_verification: dict = field(default_factory=dict)
    question_review: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    status: str = "BROWSER_OPEN"
    application_url: str = ""
    fields: list[dict] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)
    message: str | None = None
    automation_notes: list[str] = field(default_factory=list)
    resume_attached: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ApplicationSessionManager:
    def __init__(self):
        self.sessions: dict[str, BrowserSession] = {}
        self.ttl_seconds = int(os.getenv("JOBPILOT_APPLICATION_SESSION_TTL_SECONDS", "2700"))
        self.headless = os.getenv("JOBPILOT_BROWSER_HEADLESS", "false").lower() in {"1", "true", "yes"}

    async def prepare(self, application_id: str, job_url: str, career_profile: dict,
                      resume_base64: str, resume_filename: str = "tailored-resume.pdf",
                      tailored_resume: dict | None = None) -> dict:
        _validate_greenhouse_url(job_url)
        await self._expire_stale_sessions()
        extension = Path(resume_filename).suffix.lower()
        if extension not in {".pdf", ".docx"}:
            raise ApplicationAutomationError("The tailored resume must be a PDF or DOCX file.")
        try:
            resume_bytes = base64.b64decode(resume_base64, validate=True)
        except Exception as exc:
            raise ApplicationAutomationError("The tailored resume payload is invalid.") from exc
        valid_pdf = extension == ".pdf" and resume_bytes.startswith(b"%PDF")
        valid_docx = extension == ".docx" and resume_bytes.startswith(b"PK")
        if not (valid_pdf or valid_docx) or len(resume_bytes) > 12 * 1024 * 1024:
            raise ApplicationAutomationError("The selected tailored resume is invalid or exceeds 12 MB.")

        upload_dir = Path(tempfile.gettempdir()) / "jobpilot-applications"
        upload_dir.mkdir(parents=True, exist_ok=True)
        upload_path = upload_dir / f"{application_id}{extension}"
        upload_path.write_bytes(resume_bytes)

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
                career_profile=career_profile,
                tailored_resume=tailored_resume or {},
                application_url=page.url,
            )
            self.sessions[application_id] = session
            await self._run_agentic_form_completion(session)
            session.missing_required_fields = self._missing_required(session.fields)
            session.status = "NEEDS_USER_INPUT" if session.missing_required_fields else "READY_FOR_REVIEW"
            if await self._has_challenge(page):
                session.status = "NEEDS_USER_INPUT"
                session.message = "A verification or bot-check prompt is visible. Complete it manually in Chromium."
            elif session.missing_required_fields:
                session.message = "Complete the remaining required fields in the visible Chromium window, then refresh this review."
            else:
                session.message = "Review the complete form in Chromium before submitting."
            if session.automation_notes:
                session.message = (session.message or "") + " " + " ".join(session.automation_notes)
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

    async def refresh(
        self,
        session_id: str,
        career_profile: dict | None = None,
        tailored_resume: dict | None = None,
    ) -> dict:
        session = self._get_session(session_id)
        async with session.lock:
            await self._touch(session)
            if career_profile is not None:
                session.career_profile = career_profile
            if tailored_resume is not None:
                session.tailored_resume = tailored_resume
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
            await self._run_agentic_form_completion(session)
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
          const role = (el.getAttribute('role') || '').toLowerCase();
          const nativeType = (el.getAttribute('type') || '').toLowerCase();
          const type = role === 'checkbox' ? 'checkbox' : role === 'radio' ? 'radio' :
                       nativeType || el.tagName.toLowerCase();
          const labels = el.labels ? Array.from(el.labels).map(x => x.innerText).filter(Boolean) : [];
          const parentLabel = el.closest('label')?.innerText || '';
          const fieldsetLabel = el.closest('fieldset')?.querySelector('legend')?.innerText || '';
          const wrapper = el.closest('[data-field], .field, .form-field');
          const wrapperLabel = wrapper
            ? Array.from(wrapper.querySelectorAll('label, legend, [data-label]'))
                .map(node => (node.innerText || node.textContent || '').trim()).filter(Boolean).join(' ')
            : '';
          const labelledBy = el.getAttribute('aria-labelledby');
          const ariaText = labelledBy ? labelledBy.split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ') : '';
          const label = (fieldsetLabel || wrapperLabel || ariaText ||
                         el.getAttribute('aria-label') || labels.join(' ') || parentLabel ||
                         el.getAttribute('placeholder') || el.getAttribute('name') ||
                         el.id || 'Unlabelled field').trim();
          const required = Boolean(el.required || el.getAttribute('aria-required') === 'true');
          let filled = false;
          if (type === 'file') filled = Boolean(el.files && el.files.length);
          else if (type === 'checkbox' || type === 'radio') {
            filled = Boolean(el.checked || el.getAttribute('aria-checked') === 'true');
          }
          else if (el.tagName.toLowerCase() === 'select') filled = Boolean(el.value);
          else if (el.getAttribute('role') === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox') {
            filled = Boolean(el.getAttribute('aria-valuetext') || el.getAttribute('data-value') ||
                             el.getAttribute('data-selected-value'));
          } else filled = String(el.value || '').trim().length > 0;
          const options = el.tagName.toLowerCase() === 'select'
            ? Array.from(el.options).filter(o => o.value).map(o => ({value: o.value, text: o.textContent.trim()})).slice(0, 30)
            : type === 'radio'
              ? [{value: String(el.value || ''), text: (labels.join(' ') || parentLabel || el.getAttribute('aria-label') || '').trim()}]
              : [];
          const checked = type === 'checkbox' || type === 'radio'
            ? Boolean(el.checked || el.getAttribute('aria-checked') === 'true') : null;
          return { index, name: el.getAttribute('name') || '', id: el.id || '',
                   label: label.slice(0, 180), type, required, filled, checked, options };
        })""")
        seen_radio_groups = {}
        fields = []
        for item in rows:
            if item["type"] == "radio":
                group = item["name"] or item["label"]
                if group in seen_radio_groups:
                    existing = seen_radio_groups[group]
                    existing["filled"] = existing["filled"] or item["filled"]
                    existing["checked"] = existing["checked"] or item["checked"]
                    existing["required"] = existing["required"] or item["required"]
                    existing["options"].extend(item.get("options") or [])
                    continue
                item["options"] = list(item.get("options") or [])
                seen_radio_groups[group] = item
            item["classification"] = _classify_field(item["label"], item["name"], item["type"])
            fields.append(item)
        return fields

    def _profile_values(self, profile: dict) -> dict:
        full_name = str(profile.get("full_name") or "").strip()
        parts = full_name.split()
        location = str(profile.get("location") or "").strip()
        location_parts = [part.strip() for part in re.split(r"[,|]", location) if part.strip()]
        explicit_years = str(
            profile.get("total_experience_years")
            if profile.get("total_experience_years") is not None
            else profile.get("years_of_experience") or ""
        ).strip()
        years_match = re.match(r"^\s*(\d+(?:\.\d+)?)", explicit_years, re.I)
        experience_years = float(years_match.group(1)) if years_match else None

        profile_evidence = build_evidence(profile, {})
        technology_years = {}
        for technology in ("java", "spring_boot", "microservices", "kafka", "gcp"):
            years, _source = _direct_technology_years(profile, technology)
            if years is None:
                years, _refs = _inferred_technology_years(profile, technology, profile_evidence)
            technology_years[technology] = years

        def years_text(value):
            if value is None:
                return ""
            rounded = round(float(value), 1)
            return str(int(rounded)) if rounded.is_integer() else str(rounded)

        notice_period = str(
            profile.get("official_notice_period")
            or profile.get("notice_period")
            or profile.get("notice_period_days")
            or ""
        ).strip()
        if notice_period and re.fullmatch(r"\d+(?:\.\d+)?", notice_period):
            notice_period += " days"

        serving_notice = str(
            profile.get("currently_serving_notice")
            if profile.get("currently_serving_notice") is not None
            else profile.get("serving_notice") or ""
        ).strip()
        last_working_day = str(
            profile.get("official_last_working_day")
            or profile.get("last_working_day")
            or ""
        ).strip()
        join_availability = str(
            profile.get("join_availability")
            or profile.get("availability_to_join")
            or ""
        ).strip()
        notice_answer = ""
        serving_normalized = serving_notice.lower()
        is_serving = serving_normalized in {"yes", "true", "1", "serving"}
        is_not_serving = serving_normalized in {"no", "false", "0", "not serving"}
        # A combined notice/LWD question must remain blank until all conditional facts are known.
        if notice_period and is_not_serving:
            notice_answer = f"Official notice period: {notice_period}. Currently serving notice: no."
        elif notice_period and is_serving and last_working_day:
            notice_answer = (
                f"Official notice period: {notice_period}. Currently serving notice: yes. "
                f"Official last working day: {last_working_day}."
            )
        lwd_answer = last_working_day or (
            "Not currently serving notice." if is_not_serving else ""
        )

        currency = str(profile.get("ctc_currency") or "INR").strip().upper()

        def ctc_values(key):
            raw = str(profile.get(key) or "").strip()
            match = re.search(r"(?<!\w)(\d+(?:\.\d+)?)", raw.replace(",", ""))
            if not match:
                return "", ""
            amount = float(match.group(1))
            numeric = str(int(amount)) if amount.is_integer() else str(amount)
            return f"{currency} {numeric} LPA", numeric

        current_ctc, current_ctc_numeric = ctc_values("current_ctc_lpa")
        expected_ctc, expected_ctc_numeric = ctc_values("expected_ctc_lpa")

        spring_boot_microservices = ""
        spring_boot_years = technology_years["spring_boot"]
        microservices_years = technology_years["microservices"]
        if spring_boot_years is not None and microservices_years is not None:
            spring_boot_microservices = (
                f"Spring Boot: {years_text(spring_boot_years)} years; "
                f"Microservices: {years_text(microservices_years)} years"
            )

        return {
            "full_name": full_name,
            "first_name": parts[0] if parts else "",
            "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
            "email": str(profile.get("email") or "").strip(),
            "phone": str(profile.get("phone") or profile.get("mobile") or "").strip(),
            "linkedin": str(profile.get("linkedin_url") or profile.get("linkedin") or "").strip(),
            "github": str(profile.get("github_url") or profile.get("github") or "").strip(),
            "website": str(profile.get("website") or profile.get("portfolio_url") or "").strip(),
            # Prefer the explicit city field; split a multi-part location only when unambiguous.
            "city": str(profile.get("city") or profile.get("location_city") or (
                location_parts[0] if len(location_parts) >= 2 else ""
            )).strip(),
            "country": str(profile.get("country") or (
                location_parts[-1] if len(location_parts) >= 2 else ""
            )).strip(),
            "experience_years": experience_years,
            "years_java": years_text(technology_years["java"]),
            "years_spring_boot": years_text(spring_boot_years),
            "years_microservices": years_text(microservices_years),
            "years_spring_boot_microservices": spring_boot_microservices,
            "years_kafka": years_text(technology_years["kafka"]),
            "years_gcp": years_text(technology_years["gcp"]),
            "notice_period": notice_period,
            "notice_period_answer": notice_answer,
            "last_working_day": last_working_day,
            "last_working_day_answer": lwd_answer,
            "join_availability": join_availability,
            "current_ctc": current_ctc,
            "current_ctc_numeric": current_ctc_numeric,
            "expected_ctc": expected_ctc,
            "expected_ctc_numeric": expected_ctc_numeric,
        }

    async def _autofill(self, session: BrowserSession, career_profile: dict) -> int:
        """Fill only blank fields with one unambiguous value from the user's verified profile."""
        values = self._profile_values(career_profile)
        filled_count = 0
        selected_calling_code = await self._select_phone_country_code(session, values.get("phone", ""))

        phone_value = values.get("phone", "")
        if selected_calling_code:
            phone_value = _national_number(values.get("phone", ""), selected_calling_code)
            self._add_note(
                session,
                f"Selected phone country code +{selected_calling_code} from the verified international phone number."
            )
        elif any(item["classification"] == "phone_country_code" for item in session.fields):
            self._add_note(
                session,
                "Could not safely match the phone country code to the verified phone number; choose it manually."
            )

        checkbox_fields = [item for item in session.fields if item["type"] == "checkbox"]
        if checkbox_fields:
            self._add_note(
                session,
                f"Checkbox review: {len(checkbox_fields)} checkbox field(s) were detected and left for your explicit choice in Chromium. "
                "JobPilot does not assume consent, eligibility, or screening answers."
            )

        for item in session.fields:
            classification = item["classification"]
            input_type = item["type"]
            if item["filled"] or input_type in {
                "file", "checkbox", "radio", "button", "div", "span", "hidden"
            }:
                continue
            if classification in {"manual", "sensitive_or_eligibility", "phone_country_code"}:
                continue

            control = session.frame.locator(FIELD_SELECTOR).nth(item["index"])
            try:
                if input_type == "select" and classification in {
                    "country", "city", "experience_range", "years_java", "years_spring_boot",
                    "years_microservices", "years_kafka", "years_gcp", "notice_period",
                    "join_availability", "current_ctc", "expected_ctc",
                }:
                    options = await control.locator("option").evaluate_all(
                        "elements => elements.map(el => ({value: el.value, text: (el.textContent || '').trim()}))"
                    )
                    if classification in {"country", "city", "notice_period", "join_availability"}:
                        desired_key = {
                            "country": "country",
                            "city": "city",
                            "notice_period": "notice_period",
                            "join_availability": "join_availability",
                        }[classification]
                        desired = values.get(desired_key, "")
                        normalized = re.sub(r"[^a-z0-9]", "", str(desired).lower())
                        matches = [
                            option for option in options
                            if option.get("value") and normalized
                            and re.sub(r"[^a-z0-9]", "", str(option.get("text") or "").lower()) == normalized
                        ]
                    else:
                        years_key = {
                            "experience_range": "experience_years",
                            "years_java": "years_java",
                            "years_spring_boot": "years_spring_boot",
                            "years_microservices": "years_microservices",
                            "years_kafka": "years_kafka",
                            "years_gcp": "years_gcp",
                            "current_ctc": "current_ctc_numeric",
                            "expected_ctc": "expected_ctc_numeric",
                        }[classification]
                        years = values.get(years_key)
                        try:
                            years_number = float(years) if years not in (None, "") else None
                        except (TypeError, ValueError):
                            years_number = None
                        if years_number is None:
                            continue
                        match = _match_experience_range_option(options, years_number)
                        matches = [match] if match else []

                    if len(matches) == 1:
                        await control.select_option(value=matches[0]["value"])
                        filled_count += 1
                    elif classification in {"country", "city", "notice_period", "join_availability"} and desired:
                        self._add_note(
                            session,
                            f"{classification.replace('_', ' ').title()}: no exact Greenhouse option matched the verified profile value {desired!r}; choose it manually."
                        )
                    continue

                if classification == "city":
                    value = values.get("city", "")
                elif classification == "phone":
                    value = phone_value
                elif classification == "notice_period":
                    question_text = str(item.get("label") or "").lower()
                    compound_notice_question = "last working day" in question_text or "serving notice" in question_text
                    if input_type == "number":
                        notice_digits = re.search(r"\d+(?:\.\d+)?", values.get("notice_period", ""))
                        value = notice_digits.group(0) if notice_digits else ""
                    elif compound_notice_question:
                        value = values.get("notice_period_answer", "")
                    else:
                        value = values.get("notice_period", "")
                elif classification == "last_working_day":
                    value = (
                        values.get("last_working_day_answer", "")
                        if input_type != "date"
                        else values.get("last_working_day", "")
                    )
                elif classification == "current_ctc":
                    value = values.get("current_ctc_numeric" if input_type == "number" else "current_ctc", "")
                elif classification == "expected_ctc":
                    value = values.get("expected_ctc_numeric" if input_type == "number" else "expected_ctc", "")
                elif classification == "years_spring_boot_microservices":
                    value = values.get("years_spring_boot_microservices", "")
                else:
                    value = values.get(classification, "")

                if not value:
                    continue
                if input_type not in {"text", "email", "tel", "url", "textarea", "number", "date"}:
                    continue
                await control.fill(value)
                filled_count += 1
            except Exception:
                # A failed locator or re-render is retried by the next verification pass.
                continue

        manual_dropdowns = [
            item for item in session.fields
            if item["type"] == "select" and item["classification"] in {"manual", "sensitive_or_eligibility"}
            and not item["filled"]
        ]
        if manual_dropdowns:
            self._add_note(
                session,
                "Job-specific screening and eligibility dropdowns were left for your manual choice; JobPilot will not guess these answers."
            )

        await self._upload_resume(session)
        return filled_count

    async def _run_agentic_form_completion(self, session: BrowserSession):
        """Observe, safely repair, and verify the live form in three bounded passes."""
        pass_results = []
        for pass_number in range(1, 4):
            await session.page.wait_for_timeout(200)
            current_frame = await self._find_application_frame(session.page)
            if current_frame is not None:
                session.frame = current_frame

            session.fields = await self._snapshot_fields(session.frame)
            safe_fills = await self._autofill(session, session.career_profile)
            await session.page.wait_for_timeout(250)
            session.fields = await self._snapshot_fields(session.frame)
            session.missing_required_fields = self._missing_required(session.fields)

            pass_results.append({
                "pass": pass_number,
                "fields_checked": len(session.fields),
                "safe_fills": safe_fills,
                "required_fields_remaining": len(session.missing_required_fields),
            })

        session.form_verification = {
            "passes_completed": len(pass_results),
            "passes_required": 3,
            "required_fields_remaining": len(session.missing_required_fields),
            "complete": len(session.missing_required_fields) == 0,
            "pass_results": pass_results,
        }
        session.automation_notes = [
            note for note in session.automation_notes
            if not note.startswith("Form verification:")
        ]
        remaining = len(session.missing_required_fields)
        outcome = "all required fields are detected as complete" if remaining == 0 else (
            f"{remaining} required field(s) still need attention"
        )
        session.automation_notes.append(
            f"Form verification: completed 3/3 observe-and-verify passes; {outcome}. "
            "Only values from the verified profile were autofilled. Screening, eligibility, consent and unclear fields remain manual."
        )

        # Review visible questions against source evidence only after safe autofill and
        # browser re-snapshots have settled. This is advisory and never submits answers.
        session.question_review = await review_application_questions(
            session.fields,
            session.career_profile,
            getattr(session, "tailored_resume", {}),
        )
        if session.question_review.get("status") == "unavailable":
            self._add_note(
                session,
                "Question-to-profile review is unavailable right now; inspect the resume and profile manually before answering."
            )

    def _add_note(self, session: BrowserSession, note: str):
        if note not in session.automation_notes:
            session.automation_notes.append(note)

    async def _select_phone_country_code(self, session: BrowserSession, phone: str) -> str | None:
        if not phone.strip().startswith("+"):
            return None

        controls = [
            item for item in session.fields
            if item["classification"] == "phone_country_code"
        ]
        if len(controls) != 1:
            return None

        item = controls[0]
        control = session.frame.locator(FIELD_SELECTOR).nth(item["index"])
        try:
            if item["type"] == "select":
                options = await control.locator("option").evaluate_all(
                    "elements => elements.map(el => ({value: el.value, text: (el.textContent || '').trim()}))"
                )
                match = _match_country_code_option(options, phone)
                if match and match["value"]:
                    await control.select_option(value=match["value"])
                    return match["calling_code"]
                return None

            await control.click()
            options_locator = session.frame.locator("[role='option']")
            options = await options_locator.evaluate_all(
                """elements => elements.map((el, index) => ({
                    index,
                    value: el.getAttribute('data-value') || el.getAttribute('value') || '',
                    text: (el.innerText || el.textContent || '').trim()
                }))"""
            )
            match = _match_country_code_option(options, phone)
            if match:
                await options_locator.nth(match["index"]).click()
                return match["calling_code"]
        except Exception:
            return None
        return None

    async def _upload_resume(self, session: BrowserSession):
        if session.resume_attached:
            return

        # A first pass can happen before Greenhouse finishes rendering its upload
        # widget. Remove the previous diagnostic so a refresh shows current state.
        session.automation_notes = [
            note for note in session.automation_notes
            if not note.startswith("Resume upload:")
        ]

        discovered = []
        for frame in session.page.frames:
            try:
                file_inputs = frame.locator("input[type='file']")
                count = await file_inputs.count()
            except Exception:
                continue

            for index in range(count):
                candidate = file_inputs.nth(index)
                try:
                    metadata = await candidate.evaluate("""el => {
                      const labels = el.labels ? Array.from(el.labels).map(x => x.innerText).filter(Boolean) : [];
                      const parentLabel = el.closest('label')?.innerText || '';
                      const labelledBy = el.getAttribute('aria-labelledby');
                      const ariaText = labelledBy
                        ? labelledBy.split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ')
                        : '';
                      const wrapper = el.closest('[data-field], .field, .form-field') ||
                                      el.parentElement?.parentElement || el.parentElement;
                      return {
                        label: (labels.join(' ') || parentLabel || el.getAttribute('aria-label') ||
                                ariaText || el.getAttribute('placeholder') || '').trim(),
                        name: el.getAttribute('name') || '',
                        id: el.id || '',
                        accept: el.getAttribute('accept') || '',
                        parent_text: (wrapper?.innerText || '').trim().slice(0, 240)
                      };
                    }""")
                    discovered.append({
                        "frame": frame,
                        "locator": candidate,
                        "metadata": metadata,
                        "score": _resume_upload_score(metadata),
                    })
                except Exception:
                    continue

        labelled = [item for item in discovered if item["score"] >= 100]
        pdf_inputs = [item for item in discovered if item["score"] == 20]
        selected = None
        selection_reason = ""
        if len(labelled) == 1:
            selected = labelled[0]
            selection_reason = "matched the resume/CV label"
        elif len(labelled) > 1:
            session.automation_notes.append(
                "Resume upload: More than one input is labelled as a resume. Choose the correct one manually in Chromium."
            )
            return
        elif len(pdf_inputs) == 1:
            selected = pdf_inputs[0]
            selection_reason = "found the only PDF/DOCX-accepting file input"
        elif len(pdf_inputs) > 1:
            session.automation_notes.append(
                "Resume upload: Multiple PDF file inputs were found without a unique resume label. Attach the selected resume manually."
            )
            return
        elif len(discovered) == 1 and discovered[0]["score"] == 0:
            selected = discovered[0]
            selection_reason = "found the only file input on the application page"
        elif not discovered:
            session.automation_notes.append(
                "Resume upload: No HTML file input was found in any Greenhouse page frame. The upload widget may not have rendered yet; use Refresh form review to retry or attach the selected resume manually."
            )
            return
        else:
            found = [
                "label={!r}, name={!r}, id={!r}, accept={!r}".format(
                    item["metadata"]["label"][:70],
                    item["metadata"]["name"][:50],
                    item["metadata"]["id"][:50],
                    item["metadata"]["accept"][:50],
                )
                for item in discovered[:4]
            ]
            session.automation_notes.append(
                "Resume upload: File inputs were found but none could be identified safely as the resume field: "
                + "; ".join(found)
                + ". Attach the selected resume manually."
            )
            return

        accept = str(selected["metadata"].get("accept") or "").lower()
        extension = session.upload_path.suffix.lower()
        if accept:
            accepted_types = {part.strip() for part in accept.split(",") if part.strip()}
            expected_types = (
                {".pdf", "application/pdf"}
                if extension == ".pdf"
                else {".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
            )
            if not any(
                accepted in expected_types or accepted == "*/*"
                for accepted in accepted_types
            ):
                session.automation_notes.append(
                    f"Resume upload: The selected Greenhouse field does not declare support for {extension}. "
                    "Choose a supported format or attach the resume manually in Chromium."
                )
                return

        try:
            already_attached = await selected["locator"].evaluate(
                "el => Boolean(el.files && el.files.length)"
            )
            if already_attached:
                session.resume_attached = True
                session.automation_notes.append(
                    "Resume upload: A file is already present in the selected upload field; JobPilot left it unchanged."
                )
                return

            await selected["locator"].set_input_files(str(session.upload_path))
            uploaded = await selected["locator"].evaluate("""el => {
              const file = el.files && el.files.length ? el.files[0] : null;
              return file ? {name: file.name, size: file.size} : null;
            }""")
            if uploaded and uploaded["size"] > 0:
                session.resume_attached = True
                session.automation_notes.append(
                    f"Resume upload: Attached {uploaded['name']} ({uploaded['size']} bytes); {selection_reason}."
                )
            else:
                session.automation_notes.append(
                    "Resume upload: The browser accepted the file-selection call but the input still reports no selected file. Attach the selected resume manually."
                )
        except Exception as exc:
            session.automation_notes.append(
                "Resume upload: Playwright could not set the file on the selected input "
                f"({type(exc).__name__}). Attach the PDF manually and share the worker log if this repeats."
            )

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
            "automation_notes": session.automation_notes,
            "form_verification": session.form_verification,
            "question_review": session.question_review,
            "updated_at": _utc_now(),
        }


application_sessions = ApplicationSessionManager()
