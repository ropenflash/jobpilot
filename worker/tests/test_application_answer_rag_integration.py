import json
import unittest
from unittest.mock import AsyncMock, patch

from app.agents.application_question_reviewer import review_application_questions


class ApplicationAnswerRagIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_reviewer_builds_question_specific_context_and_returns_cited_answer(self):
        fields = [{
            "index": 3,
            "label": "Describe your experience with distributed systems.",
            "type": "textarea",
            "required": True,
            "filled": False,
            "classification": "manual",
        }]
        profile = {
            "skills": ["Java", "Kafka"],
            "experience": [{
                "title": "Senior Backend Engineer",
                "description": (
                    "Designed event-driven microservices and Kafka consumers for a distributed "
                    "order platform. Owned service reliability and production operations."
                ),
                "technologies": ["Java", "Spring Boot", "Kafka"],
            }],
        }
        job_context = {
            "job": {
                "title": "Staff Backend Engineer",
                "company": "Acme",
                "description": "Build distributed systems for the commerce platform.",
            },
            "requirements": {
                "summary": "Lead architecture for highly available services.",
                "required_skills": ["Java", "Kafka", "Distributed systems"],
                "responsibilities": ["Design event-driven services."],
            },
        }

        async def model_response(messages, **kwargs):
            prompt = json.loads(messages[1]["content"])
            self.assertIn("Distributed systems", prompt["job_context"]["required_skills"])
            question = prompt["questions"][0]
            retrieved = question["retrieved_evidence"]
            self.assertTrue(retrieved)
            self.assertTrue(all(item["source"] == "verified_profile" for item in retrieved))
            reference = retrieved[0]["id"]
            return json.dumps({
                "reviews": [{
                    "field_index": 3,
                    "category": "technical_experience",
                    "evidence_status": "supported",
                    "reason": "The work-history evidence describes event-driven microservices and Kafka.",
                    "evidence_refs": [reference],
                    "suggested_answer": (
                        "I designed event-driven microservices and Kafka consumers for a distributed "
                        "order platform, and owned production reliability."
                    ),
                    "profile_improvement": None,
                }],
                "profile_improvements": [],
            })

        with patch(
            "app.agents.application_question_reviewer.generate_text",
            new_callable=AsyncMock,
            side_effect=model_response,
        ) as generate:
            result = await review_application_questions(
                fields,
                profile,
                {"summary": "Backend engineer focused on distributed systems."},
                job_context,
            )

        generate.assert_awaited_once()
        review = result["reviews"][0]
        self.assertEqual(review["evidence_status"], "supported")
        self.assertEqual(review["retrieval"]["method"], "bm25_hybrid")
        self.assertGreater(review["retrieval"]["retrieved_count"], 0)
        self.assertGreater(result["rag"]["evidence_snippets_retrieved"], 0)
        self.assertTrue(result["rag"]["job_context_available"])
        self.assertEqual(review["evidence"][0]["source"], "verified_profile")

    async def test_job_requirements_alone_never_become_candidate_evidence(self):
        fields = [{
            "index": 1,
            "label": "Describe your Kubernetes experience.",
            "type": "textarea",
            "required": True,
            "filled": False,
            "classification": "manual",
        }]
        job_context = {
            "job": {"title": "Platform Engineer"},
            "requirements": {
                "required_skills": ["Kubernetes"],
                "responsibilities": ["Operate Kubernetes clusters."],
            },
        }
        with patch(
            "app.agents.application_question_reviewer.generate_text",
            new_callable=AsyncMock,
        ) as generate:
            result = await review_application_questions(fields, {}, {}, job_context)

        generate.assert_not_awaited()
        review = result["reviews"][0]
        self.assertEqual(review["evidence_status"], "not_found")
        self.assertIsNone(review["suggested_answer"])
        self.assertEqual(review["evidence"], [])
        self.assertTrue(result["rag"]["job_context_available"])


if __name__ == "__main__":
    unittest.main()
