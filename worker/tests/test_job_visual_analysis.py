import json
import unittest
from unittest.mock import AsyncMock, patch

from app.agents.job_analyzer import analyze_and_match


JOB = {
    "job_id": 123456,
    "board_token": "acme",
    "title": "Senior Backend Engineer",
    "company": "Acme",
    "location": "Remote",
    "job_url": "https://boards.greenhouse.io/acme/jobs/123456",
    "description": "Build Java and distributed systems services.",
}


class JobVisualAnalysisTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.agents.job_analyzer.generate_text", new_callable=AsyncMock)
    async def test_screenshots_are_sent_to_model_and_summary_is_returned(self, generate):
        generate.return_value = json.dumps({
            "requirements": {
                "summary": "Build backend services.",
                "required_skills": ["Java"],
            },
            "match": {
                "strengths": [],
                "gaps": ["Distributed systems experience not evidenced in the profile."],
                "evidence": [],
            },
            "visual_findings": ["The rendered page displays a hybrid-work banner."],
        })

        inspection = {
            "status": "completed",
            "screenshots": [b"first-shot", b"second-shot"],
            "page_title": "Acme Careers",
            "page_headings": ["Senior Backend Engineer", "About the role"],
            "rendered_text": "Hybrid work. Senior Backend Engineer.",
            "note": None,
        }
        result = await analyze_and_match(JOB, {"skills": ["Java"]}, inspection)

        self.assertEqual(generate.await_args.kwargs["images"], [
            ("image/jpeg", b"first-shot"),
            ("image/jpeg", b"second-shot"),
        ])
        self.assertEqual(result.visual_inspection.status, "completed")
        self.assertEqual(result.visual_inspection.screenshots_captured, 2)
        self.assertEqual(result.visual_inspection.page_title, "Acme Careers")
        self.assertEqual(
            result.visual_inspection.findings,
            ["The rendered page displays a hybrid-work banner."],
        )

    @patch("app.agents.job_analyzer.generate_text", new_callable=AsyncMock)
    async def test_text_only_mode_remains_supported(self, generate):
        generate.return_value = json.dumps({
            "requirements": {"summary": "Build backend services."},
            "match": {"strengths": [], "gaps": [], "evidence": []},
            "visual_findings": [],
        })

        result = await analyze_and_match(
            JOB,
            {"skills": ["Java"]},
            {"status": "unavailable", "screenshots": [], "note": "Chromium unavailable."},
        )

        self.assertIsNone(generate.await_args.kwargs["images"])
        self.assertEqual(result.visual_inspection.status, "unavailable")
        self.assertEqual(result.visual_inspection.screenshots_captured, 0)


if __name__ == "__main__":
    unittest.main()
