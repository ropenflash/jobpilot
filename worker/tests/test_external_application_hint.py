import unittest

from app.browser.application_manager import _external_application_hint


class ExternalApplicationHintTests(unittest.TestCase):
    def test_explicit_external_application_instruction_returns_external_link(self):
        text = "You will not be considered unless you complete the Constellation application form."
        links = [{
            "text": "Constellation application form",
            "href": "https://constellation.org/apply",
            "context": "Complete this application form.",
        }]
        self.assertEqual(_external_application_hint(text, links), "https://constellation.org/apply")

    def test_ordinary_application_page_does_not_trigger(self):
        text = "Complete the application form and upload your resume."
        links = [{
            "text": "Apply",
            "href": "https://boards.greenhouse.io/acme/jobs/123/apply",
            "context": "Apply for this role.",
        }]
        self.assertIsNone(_external_application_hint(text, links))

    def test_redirect_instruction_without_external_link_returns_none(self):
        text = "Use the provided link to complete the external application."
        self.assertIsNone(_external_application_hint(text, []))


if __name__ == "__main__":
    unittest.main()
