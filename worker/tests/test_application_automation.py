import unittest

from app.browser.application_manager import (
    ApplicationAutomationError,
    _classify_field,
    _match_country_code_option,
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

    def test_cover_letter_is_not_mistaken_for_resume(self):
        self.assertEqual(_classify_field("Cover letter", "cover_letter", "file"), "manual")

    def test_checkboxes_are_tracked_but_never_inferred(self):
        self.assertEqual(_classify_field("I agree to the privacy policy", "privacy", "checkbox"), "checkbox_review")
        self.assertEqual(
            _classify_field("Work authorization", "work_authorization", "checkbox"),
            "sensitive_or_eligibility",
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

    def test_does_not_guess_country_code_from_local_number(self):
        options = [{"value": "+91", "text": "India (+91)"}]
        self.assertIsNone(_match_country_code_option(options, "9876543210"))

    def test_ambiguous_country_code_options_are_not_selected(self):
        options = [
            {"value": "+1", "text": "United States (+1)"},
            {"value": "1", "text": "Canada (+1)"},
        ]
        self.assertIsNone(_match_country_code_option(options, "+1 4155550100"))


if __name__ == "__main__":
    unittest.main()
