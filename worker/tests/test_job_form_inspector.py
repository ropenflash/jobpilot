import unittest
from unittest.mock import AsyncMock, patch

from app.services.job_form_inspector import _compare_fields, inspect_job_form


JOB = {
    "job_id": 123,
    "board_token": "acme",
    "title": "Platform Engineer",
    "company": "Acme",
    "location": "Remote",
    "job_url": "https://boards.greenhouse.io/acme/jobs/123",
    "description": "Apply with a resume and portfolio.",
}


class JobFormInspectorTests(unittest.IsolatedAsyncioTestCase):
    def test_compare_fields_reports_overlap_and_differences(self):
        result = _compare_fields(
            [{"field": "email"}, {"field": "resume"}],
            [{"field": "email"}, {"field": "phone"}],
        )
        self.assertEqual(result["shared_fields"], ["email"])
        self.assertEqual(result["html_only_fields"], ["resume"])
        self.assertEqual(result["visual_only_fields"], ["phone"])
        self.assertEqual(result["field_count"], 3)

    @patch("app.services.job_form_inspector.inspect_visual_job_agent", new_callable=AsyncMock)
    @patch("app.services.job_form_inspector.inspect_greenhouse_job_page", new_callable=AsyncMock)
    @patch("app.services.job_form_inspector.inspect_html_job_agent", new_callable=AsyncMock)
    @patch("app.services.job_form_inspector.analyze_application_workflow", new_callable=AsyncMock)
    @patch("app.services.job_form_inspector.fetch_greenhouse_job", new_callable=AsyncMock)
    async def test_runs_two_agents_independently_and_hides_image_bytes(
        self, fetch_job, workflow_agent, html_agent, inspect_page, visual_agent
    ):
        fetch_job.return_value = JOB
        html_agent.return_value = {
            "fields": [{"field": "resume"}],
            "instructions": [],
            "limitations": [],
        }
        inspect_page.return_value = {
            "status": "completed",
            "screenshots": [b"not-returned-to-client"],
            "page_title": "Acme Careers",
            "page_headings": [],
            "rendered_text": "",
            "note": None,
        }
        visual_agent.return_value = {
            "fields": [{"field": "email"}],
            "instructions": [],
            "limitations": [],
        }
        workflow_agent.return_value = {
            "workflow_type": "standard_form",
            "confidence": 0.9,
            "rationale": "Controls were detected.",
            "required_actions": [],
            "stop_conditions": ["Do not submit."],
        }

        result = await inspect_job_form(JOB["job_url"])

        html_agent.assert_awaited_once_with(JOB)
        visual_agent.assert_awaited_once()
        workflow_agent.assert_awaited_once()
        self.assertEqual(result["workflow"]["workflow_type"], "standard_form")
        self.assertFalse(result["workflow"]["submission_performed"])
        self.assertEqual(result["comparison"]["html_only_fields"], ["resume"])
        self.assertEqual(result["comparison"]["visual_only_fields"], ["email"])
        self.assertNotIn("screenshots", result["agents"]["visual"])


if __name__ == "__main__":
    unittest.main()
