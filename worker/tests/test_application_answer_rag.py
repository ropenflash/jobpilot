import unittest

from app.agents.application_answer_rag import (
    build_job_context,
    retrieve_question_evidence,
)


class ApplicationAnswerRagTests(unittest.TestCase):
    def test_semantic_expansion_retrieves_kafka_microservices_for_distributed_systems(self):
        evidence = [
            {
                "id": "verified_profile:experience[0].description",
                "source": "verified_profile",
                "path": "experience[0].description",
                "text": "Designed event-driven microservices and Kafka consumers for an order processing platform.",
            },
            {
                "id": "verified_profile:education[0].degree",
                "source": "verified_profile",
                "path": "education[0].degree",
                "text": "Bachelor of Technology in Computer Science.",
            },
        ]
        result = retrieve_question_evidence(
            {
                "question": "Describe your experience building distributed systems.",
                "classification": "manual",
            },
            evidence,
        )
        self.assertEqual(result["retrieved_count"], 1)
        self.assertEqual(
            result["items"][0]["id"],
            "verified_profile:experience[0].description",
        )

    def test_job_context_is_used_for_question_intent_but_is_not_returned_as_candidate_evidence(self):
        evidence = [{
            "id": "verified_profile:experience[0].description",
            "source": "verified_profile",
            "path": "experience[0].description",
            "text": "Built scalable Java services and operated them in production.",
        }]
        result = retrieve_question_evidence(
            {"question": "How would you contribute to this role?", "classification": "manual"},
            evidence,
            {
                "title": "Senior Backend Engineer",
                "summary": "Own distributed systems and event-driven services.",
                "required_skills": ["Java", "Kafka"],
            },
        )
        self.assertGreater(result["retrieved_count"], 0)
        self.assertIn("Java", result["job_context"]["required_skills"])
        self.assertTrue(all(item["source"] == "verified_profile" for item in result["items"]))

    def test_build_job_context_accepts_nested_stored_job_and_flattened_context(self):
        nested = build_job_context({
            "job": {
                "title": "Staff Engineer",
                "description": "Design platform services.",
            },
            "requirements": {
                "summary": "Own architecture.",
                "required_skills": ["Java"],
                "responsibilities": ["Lead system design."],
            },
        })
        flattened = build_job_context(nested)
        self.assertEqual(nested["title"], flattened["title"])
        self.assertEqual(nested["summary"], flattened["summary"])
        self.assertEqual(nested["required_skills"], flattened["required_skills"])
        self.assertIn("Design platform services.", flattened["description_excerpt"])


if __name__ == "__main__":
    unittest.main()
