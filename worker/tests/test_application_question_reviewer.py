import unittest
from unittest.mock import AsyncMock, patch

from app.agents.application_question_reviewer import (
    build_evidence,
    build_questions,
    normalize_review,
    review_application_questions,
)


class ApplicationQuestionReviewerTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "full_name": "Candidate Example",
            "skills": ["Java", "Kafka", "PostgreSQL"],
            "experience": [
                {
                    "title": "Senior Engineer",
                    "company": "Example Co",
                    "description": "Built Spring Boot microservices and Kafka event pipelines.",
                }
            ],
        }
        self.resume = {
            "summary": "Backend engineer focused on distributed systems.",
            "experience": [
                {
                    "title": "Senior Engineer",
                    "bullets": [
                        {"text": "Designed Kafka consumers for event-driven services."}
                    ],
                }
            ],
        }

    def test_build_evidence_keeps_source_paths(self):
        evidence = build_evidence(self.profile, self.resume)
        ids = {item["id"] for item in evidence}
        self.assertIn("verified_profile:skills[0]", ids)
        self.assertIn("verified_profile:experience[0].description", ids)
        self.assertIn("tailored_resume:summary", ids)

    def test_build_questions_preserves_radio_options_and_question_ids(self):
        questions = build_questions([{
            "index": 6,
            "label": "What is your software experience range?",
            "type": "radio",
            "required": True,
            "classification": "experience_range",
            "options": [
                {"value": "11-15", "text": "11-15 years"},
                {"value": "16+", "text": "16+ years"},
            ],
        }])
        self.assertEqual(questions[0]["field_index"], 6)
        self.assertEqual(questions[0]["options"][0]["text"], "11-15 years")

    def test_supported_answer_requires_a_valid_evidence_reference(self):
        evidence = build_evidence(self.profile, self.resume)
        question = {
            "field_index": 4,
            "question": "Describe your Kafka experience.",
            "required": True,
            "classification": "manual",
        }
        valid_ref = next(
            item["id"] for item in evidence
            if item["path"] == "experience[0].description"
        )
        result = normalize_review({
            "reviews": [{
                "field_index": 4,
                "category": "technical_experience",
                "evidence_status": "supported",
                "reason": "The profile describes Kafka event pipelines.",
                "evidence_refs": [valid_ref],
                "suggested_answer": "I built Kafka event pipelines.",
                "profile_improvement": None,
            }]
        }, [question], evidence)
        self.assertEqual(result["reviews"][0]["evidence_status"], "supported")
        self.assertEqual(result["reviews"][0]["evidence"][0]["source"], "verified_profile")

        unsupported = normalize_review({
            "reviews": [{
                "field_index": 4,
                "category": "technical_experience",
                "evidence_status": "supported",
                "reason": "No valid reference was supplied.",
                "evidence_refs": ["made-up:source"],
                "suggested_answer": "I led a 50-person team.",
                "profile_improvement": None,
            }]
        }, [question], evidence)
        self.assertEqual(unsupported["reviews"][0]["evidence_status"], "not_found")
        self.assertIsNone(unsupported["reviews"][0]["suggested_answer"])

    def test_missing_evidence_creates_truthful_profile_improvement_guidance(self):
        question = {
            "field_index": 2,
            "question": "Describe your experience with Kubernetes.",
            "required": True,
            "classification": "manual",
        }
        result = normalize_review({
            "reviews": [{
                "field_index": 2,
                "category": "technical_experience",
                "evidence_status": "not_found",
                "reason": "No Kubernetes evidence was found.",
                "evidence_refs": [],
                "suggested_answer": None,
                "profile_improvement": "If applicable, add a project showing your Kubernetes responsibilities.",
            }]
        }, [question], [])
        review = result["reviews"][0]
        self.assertEqual(review["evidence_status"], "not_found")
        self.assertIsNone(review["suggested_answer"])
        self.assertIn("Kubernetes", review["profile_improvement"])


class ApplicationQuestionSensitiveGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_sensitive_consent_questions_are_not_sent_to_ai_for_answering(self):
        fields = [{
            "index": 10,
            "label": "I agree to the Candidate Privacy Notice",
            "type": "checkbox",
            "required": True,
            "classification": "checkbox_review",
        }]
        with patch(
            "app.agents.application_question_reviewer.generate_text",
            new_callable=AsyncMock,
        ) as generate:
            result = await review_application_questions(
                fields,
                {"skills": ["Java"]},
                {},
            )
        generate.assert_not_awaited()
        self.assertEqual(result["reviews"][0]["evidence_status"], "manual_review")
        self.assertIsNone(result["reviews"][0]["suggested_answer"])


if __name__ == "__main__":
    unittest.main()
