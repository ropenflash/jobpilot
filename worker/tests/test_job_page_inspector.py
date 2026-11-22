import os
import unittest
from unittest.mock import patch

from app.services.job_page_inspector import (
    _screenshot_limit,
    _screenshot_offsets,
    inspect_greenhouse_job_page,
)


class JobPageInspectionTests(unittest.IsolatedAsyncioTestCase):
    def test_screenshot_offsets_cover_top_and_lower_sections_without_duplicates(self):
        self.assertEqual(_screenshot_offsets(800, 1000, 4), [0])
        offsets = _screenshot_offsets(2800, 1000, 4)
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets[-1], 1800)
        self.assertEqual(len(offsets), len(set(offsets)))
        self.assertLessEqual(len(offsets), 4)

    def test_screenshot_limit_is_bounded(self):
        with patch.dict(os.environ, {"JOBPILOT_JOB_SCREENSHOT_COUNT": "99"}):
            self.assertEqual(_screenshot_limit(), 5)
        with patch.dict(os.environ, {"JOBPILOT_JOB_SCREENSHOT_COUNT": "0"}):
            self.assertEqual(_screenshot_limit(), 1)
        with patch.dict(os.environ, {"JOBPILOT_JOB_SCREENSHOT_COUNT": "bad"}):
            self.assertEqual(_screenshot_limit(), 4)

    async def test_disabled_inspection_does_not_launch_browser(self):
        with patch.dict(os.environ, {"JOBPILOT_JOB_VISUAL_INSPECTION_ENABLED": "false"}):
            result = await inspect_greenhouse_job_page(
                "https://boards.greenhouse.io/acme/jobs/123456"
            )
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["screenshots"], [])
        self.assertIsNone(result["page_title"])

    async def test_non_greenhouse_url_is_rejected_before_browser_launch(self):
        with patch.dict(os.environ, {"JOBPILOT_JOB_VISUAL_INSPECTION_ENABLED": "true"}):
            with self.assertRaises(Exception):
                await inspect_greenhouse_job_page("https://example.com/jobs/123456")


if __name__ == "__main__":
    unittest.main()
