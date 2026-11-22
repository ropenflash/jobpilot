import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.browser.application_manager import (
    ApplicationAutomationError,
    ApplicationSessionManager,
    _classify_field,
    _match_country_code_option,
    _match_experience_range_option,
    _national_number,
    _resume_upload_score,
    _validate_greenhouse_url,
)


class ApplicationAutomationTests(unittest.TestCase):
    def test_accepts_only_public_greenhouse_job_urls(self):
        self.assertEqual(
            _validate_greenhouse_url("https://boards.greenhouse.io/acme/jobs/12345"),
            "https://boards.greenhouse.io/acme/jobs/12345",
        )
        self.assertEqual(
            _validate_greenhouse_url("https://job-boards.greenhouse.io/acme/jobs/12345"),
            "https://job-boards.greenhouse.io/acme/jobs/12345",
        )

    def test_rejects_non_greenhouse_and_non_job_urls(self):
        for value in (
            "https://example.com/acme/jobs/12345",
            "http://boards.greenhouse.io/acme/jobs/12345",
            "https://boards.greenhouse.io/acme",
            "https://boards.greenhouse.io.evil.example/acme/jobs/12345",
        ):
            with self.subTest(value=value), self.assertRaises(ApplicationAutomationError):
                _validate_greenhouse_url(value)

    def test_field_classifier_never_autofills_sensitive_fields(self):
        self.assertEqual(_classify_field("First Name", "first_name", "text"), "first_name")
        self.assertEqual(_classify_field("Email", "email", "email"), "email")
        self.assertEqual(
            _classify_field("Gender identity", "gender", "select"),
            "sensitive_or_eligibility",
        )
        self.assertEqual(_classify_field("Resume/CV", "resume", "file"), "resume")
        self.assertEqual(_classify_field("Country code", "phone_country_code", "select"), "phone_country_code")
        self.assertEqual(
            _classify_field("What experience range do you carry in your professional software experience?", "experience", "select"),
            "experience_range",
        )
        self.assertEqual(
            _classify_field("Have you previously been employed by AlphaSense?", "employer_history", "radio"),
            "sensitive_or_eligibility",
        )

    def test_cover_letter_is_not_mistaken_for_resume(self):
        self.assertEqual(_classify_field("Cover letter", "cover_letter", "file"), "manual")

    def test_checkboxes_are_tracked_but_never_inferred(self):
        self.assertEqual(_classify_field("I agree to the privacy policy", "privacy", "checkbox"), "checkbox_review")
        self.assertEqual(
            _classify_field("Work authorization", "work_authorization", "checkbox"),
            "sensitive_or_eligibility",
        )

    def test_required_unchecked_checkbox_blocks_application_review(self):
        manager = ApplicationSessionManager()
        fields = [
            {"label": "I agree to the privacy policy", "required": True, "filled": False},
            {"label": "Optional newsletter", "required": False, "filled": False},
            {"label": "I confirm the information is accurate", "required": True, "filled": True},
        ]
        self.assertEqual(
            manager._missing_required(fields),
            ["I agree to the privacy policy"],
        )

    def test_matches_country_code_from_international_phone(self):
        options = [
            {"value": "+1", "text": "United States (+1)"},
            {"value": "+91", "text": "India (+91)"},
            {"value": "+44", "text": "United Kingdom (+44)"},
        ]
        match = _match_country_code_option(options, "+91 9876543210")
        self.assertEqual(match["calling_code"], "91")
        self.assertEqual(_national_number("+91 9876543210", "91"), "9876543210")

    def test_resume_upload_score_prefers_resume_field_and_rejects_cover_letter(self):
        self.assertEqual(_resume_upload_score({"label": "Resume / CV"}), 100)
        self.assertEqual(_resume_upload_score({"label": "Cover letter", "accept": ".pdf"}), -1)
        self.assertEqual(_resume_upload_score({"label": "Upload a file", "accept": ".pdf"}), 20)
        self.assertEqual(_resume_upload_score({"label": "Upload a file", "accept": ".docx"}), 20)

    def test_experience_range_is_selected_only_when_the_verified_years_match_one_option(self):
        options = [
            {"value": "0-5", "text": "0-5 years"},
            {"value": "6-10", "text": "6-10 years"},
            {"value": "11-15", "text": "11-15 years"},
            {"value": "16+", "text": "16+ years"},
        ]
        self.assertEqual(_match_experience_range_option(options, 11)["value"], "11-15")
        self.assertEqual(_match_experience_range_option(options, 5)["value"], "0-5")
        overlapping = [
            {"value": "0-5", "text": "0-5 years"},
            {"value": "5-10", "text": "5-10 years"},
        ]
        self.assertIsNone(_match_experience_range_option(overlapping, 5))

    def test_profile_values_split_only_a_multi_part_verified_location(self):
        values = ApplicationSessionManager()._profile_values({
            "location": "Noida, Uttar Pradesh, India",
            "linkedin_url": "https://www.linkedin.com/in/example",
            "total_experience_years": 11,
        })
        self.assertEqual(values["city"], "Noida")
        self.assertEqual(values["country"], "India")
        self.assertEqual(values["experience_years"], 11.0)
        approximate = ApplicationSessionManager()._profile_values({"total_experience_years": "11+ years"})
        self.assertEqual(approximate["experience_years"], 11.0)
        self.assertEqual(values["linkedin"], "https://www.linkedin.com/in/example")

    def test_does_not_guess_country_code_from_local_number(self):
        options = [{"value": "+91", "text": "India (+91)"}]
        self.assertIsNone(_match_country_code_option(options, "9876543210"))

    def test_ambiguous_country_code_options_are_not_selected(self):
        options = [
            {"value": "+1", "text": "United States (+1)"},
            {"value": "1", "text": "Canada (+1)"},
        ]
        self.assertIsNone(_match_country_code_option(options, "+1 4155550100"))


class AgenticFormVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_runs_three_observe_fill_verify_passes(self):
        manager = ApplicationSessionManager()

        class FakePage:
            async def wait_for_timeout(self, _milliseconds):
                return None

        session = SimpleNamespace(
            page=FakePage(),
            frame=object(),
            career_profile={},
            fields=[],
            missing_required_fields=[],
            automation_notes=[],
            form_verification={},
        )
        manager._find_application_frame = AsyncMock(return_value=session.frame)
        manager._snapshot_fields = AsyncMock(return_value=[
            {"label": "Email", "required": True, "filled": False}
        ])
        manager._autofill = AsyncMock(return_value=0)

        await manager._run_agentic_form_completion(session)

        self.assertEqual(manager._snapshot_fields.await_count, 6)
        self.assertEqual(manager._autofill.await_count, 3)
        self.assertEqual(session.form_verification["passes_completed"], 3)
        self.assertEqual(session.form_verification["required_fields_remaining"], 1)
        self.assertFalse(session.form_verification["complete"])
        self.assertEqual(
            [item["pass"] for item in session.form_verification["pass_results"]],
            [1, 2, 3],
        )


if __name__ == "__main__":
    unittest.main()
