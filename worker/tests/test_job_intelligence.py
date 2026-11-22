import unittest

from fastapi import HTTPException

from app.agents.job_analyzer import _score_evidence
from app.schemas.job import MatchEvidence
from app.services.greenhouse import html_to_text, parse_greenhouse_job_url


class GreenhouseUrlTests(unittest.TestCase):
    def test_parses_standard_greenhouse_job_url(self):
        self.assertEqual(
            parse_greenhouse_job_url(
                "https://boards.greenhouse.io/acme/jobs/123456?gh_src=abc"
            ),
            ("acme", 123456),
        )

    def test_parses_alternate_greenhouse_host(self):
        self.assertEqual(
            parse_greenhouse_job_url(
                "https://job-boards.greenhouse.io/acme-platform/jobs/987"
            ),
            ("acme-platform", 987),
        )

    def test_rejects_non_greenhouse_host(self):
        with self.assertRaises(HTTPException):
            parse_greenhouse_job_url("https://boards.greenhouse.io.attacker.example/acme/jobs/123")

    def test_rejects_http_and_malformed_paths(self):
        for url in (
            "http://boards.greenhouse.io/acme/jobs/123",
            "https://boards.greenhouse.io/acme/apply/123",
        ):
            with self.subTest(url=url), self.assertRaises(HTTPException):
                parse_greenhouse_job_url(url)

    def test_html_is_converted_without_script_or_style_content(self):
        text = html_to_text(
            "<h2>Responsibilities</h2><p>Build <strong>Java</strong> services.</p>"
            "<script>ignore_this()</script><style>.secret{}</style>"
            "<ul><li>Own production systems</li></ul>"
        )
        self.assertIn("Responsibilities", text)
        self.assertIn("Build Java services.", text)
        self.assertIn("Own production systems", text)
        self.assertNotIn("ignore_this", text)
        self.assertNotIn(".secret", text)


class MatchScoringTests(unittest.TestCase):
    def test_score_is_calculated_from_evidence_and_weights_sum_to_100(self):
        evidence = [
            MatchEvidence(
                category="required_skill",
                requirement="Java",
                profile_evidence="Java in recent role",
                assessment="matched",
            ),
            MatchEvidence(
                category="experience_responsibilities",
                requirement="Architecture ownership",
                profile_evidence="Related technical ownership",
                assessment="partial",
            ),
            MatchEvidence(
                category="preferred_skill",
                requirement="Kubernetes",
                profile_evidence="Not evidenced in profile",
                assessment="not_evidenced",
            ),
        ]
        score, breakdown = _score_evidence(evidence)
        self.assertEqual(score, 69)
        self.assertEqual(sum(item.weight_percentage for item in breakdown), 100)

    def test_empty_evidence_has_no_match_score(self):
        score, breakdown = _score_evidence([])
        self.assertEqual(score, 0)
        self.assertEqual(breakdown, [])


if __name__ == "__main__":
    unittest.main()
