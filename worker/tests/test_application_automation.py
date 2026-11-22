import unittest

from app.browser.application_manager import (
    ApplicationAutomationError,
    _classify_field,
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

    def test_cover_letter_is_not_mistaken_for_resume(self):
        self.assertEqual(_classify_field("Cover letter", "cover_letter", "file"), "manual")


if __name__ == "__main__":
    unittest.main()
