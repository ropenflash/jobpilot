import unittest

from app.agents.application_answer_resolver import (
    _inferred_technology_years,
    resolve_structured_question,
)
from app.agents.application_question_reviewer import build_evidence, review_application_questions


class StructuredApplicationAnswerResolverTests(unittest.TestCase):
    def _question(self, label, classification, index=0):
        return {
            "field_index": index,
            "question": label,
            "classification": classification,
            "required": True,
        }

    def test_contact_location_technology_notice_and_ctc_answers_use_explicit_profile_values(self):
        profile = {
            "phone": "+91 9876543210",
            "location": "Greater Noida, Uttar Pradesh, India",
            "java_experience_years": "8",
            "spring_boot_experience_years": "6",
            "microservices_experience_years": "5",
            "kafka_experience_years": "4",
            "gcp_experience_years": "3",
            "official_notice_period": "60 days",
            "currently_serving_notice": "yes",
            "official_last_working_day": "2026-12-31",
            "join_availability": "From 2027-01-01",
            "current_ctc_lpa": "47",
            "expected_ctc_lpa": "65",
            "ctc_currency": "INR",
        }
        evidence = build_evidence(profile, {})

        cases = [
            ("Phone", "phone", "+91 9876543210"),
            ("Location (City)", "city", "Greater Noida"),
            ("Java development experience", "years_java", "8 years"),
            ("Spring Boot and Microservices", "years_spring_boot_microservices",
             "Spring Boot: 6 years; Microservices: 5 years"),
            ("Kafka experience", "years_kafka", "4 years"),
            ("GCP experience", "years_gcp", "3 years"),
            ("Official notice period and last working day", "notice_period",
             "Official notice period: 60 days. Currently serving notice: yes. Official last working day: 2026-12-31."),
            ("How soon can you join us?", "join_availability", "From 2027-01-01"),
            ("Current CTC", "current_ctc", "INR 47 LPA"),
            ("Expected CTC", "expected_ctc", "INR 65 LPA"),
        ]
        for index, (label, classification, expected) in enumerate(cases):
            with self.subTest(label=label):
                result = resolve_structured_question(
                    self._question(label, classification, index),
                    profile,
                    evidence,
                )
                self.assertEqual(result["evidence_status"], "supported")
                self.assertEqual(result["suggested_answer"], expected)
                self.assertFalse(result["needs_profile_update"])
                self.assertTrue(result["evidence"])

    def test_skill_duration_can_be_approximated_from_dated_roles_and_overlaps_count_once(self):
        profile = {
            "experience": [
                {
                    "title": "Software Engineer",
                    "start_date": "Jan 2018",
                    "end_date": "Dec 2020",
                    "description": "Developed Java services and Kafka consumers.",
                    "technologies": ["Java", "Kafka"],
                },
                {
                    "title": "Senior Engineer",
                    "start_date": "Jan 2019",
                    "end_date": "Dec 2021",
                    "description": "Continued Java platform development.",
                    "technologies": ["Java"],
                },
            ]
        }
        evidence = build_evidence(profile, {})
        years, refs = _inferred_technology_years(profile, "java", evidence)
        self.assertEqual(years, 4.0)
        self.assertTrue(any("start_date" in ref for ref in refs))
        result = resolve_structured_question(
            self._question("How many years of Java development?", "years_java"),
            profile,
            evidence,
        )
        self.assertEqual(result["evidence_status"], "supported")
        self.assertEqual(result["suggested_answer"], "4 years")
        self.assertIn("Approximate", result["reason"])

    def test_skills_list_alone_does_not_create_a_years_estimate(self):
        profile = {"skills": ["Java", "Kafka", "GCP"]}
        result = resolve_structured_question(
            self._question("How many years of Kafka experience?", "years_kafka"),
            profile,
            build_evidence(profile, {}),
        )
        self.assertEqual(result["evidence_status"], "not_found")
        self.assertTrue(result["needs_profile_update"])
        self.assertIn("kafka_experience_years", result["profile_fields_needed"])
        self.assertIsNone(result["suggested_answer"])

    def test_notice_period_requires_notice_status_and_last_working_day_when_serving(self):
        profile = {
            "official_notice_period": "90 days",
            "currently_serving_notice": "yes",
        }
        result = resolve_structured_question(
            self._question("Official notice period and LWD", "notice_period"),
            profile,
            build_evidence(profile, {}),
        )
        self.assertEqual(result["evidence_status"], "partial")
        self.assertIn("official_last_working_day", result["profile_fields_needed"])
        self.assertIn("90 days", result["suggested_answer"])

    def test_join_date_is_not_assumed_from_notice_period_alone(self):
        profile = {
            "official_notice_period": "60 days",
            "currently_serving_notice": "no",
        }
        result = resolve_structured_question(
            self._question("How soon can you join?", "join_availability"),
            profile,
            build_evidence(profile, {}),
        )
        self.assertEqual(result["evidence_status"], "not_found")
        self.assertIn("join_availability", result["profile_fields_needed"])

    def test_lwd_can_be_conditional_when_not_serving_notice(self):
        profile = {"currently_serving_notice": "no"}
        result = resolve_structured_question(
            self._question("Official last working day if serving notice", "last_working_day"),
            profile,
            build_evidence(profile, {}),
        )
        self.assertEqual(result["evidence_status"], "supported")
        self.assertEqual(result["suggested_answer"], "Not currently serving notice.")

    def test_compensation_is_never_guessed_from_resume_or_experience(self):
        profile = {"total_experience_years": 11, "headline": "Senior Engineer"}
        result = resolve_structured_question(
            self._question("What is your current CTC?", "current_ctc"),
            profile,
            build_evidence(profile, {}),
        )
        self.assertEqual(result["evidence_status"], "not_found")
        self.assertIn("current_ctc_lpa", result["profile_fields_needed"])
        self.assertIsNone(result["suggested_answer"])

    def test_unlabelled_field_is_manual_not_fabricated(self):
        result = resolve_structured_question(
            self._question("Unlabelled field", "unlabelled_field"),
            {},
            [],
        )
        self.assertEqual(result["evidence_status"], "manual_review")
        self.assertIsNone(result["suggested_answer"])
        self.assertFalse(result["needs_profile_update"])


class StructuredQuestionReviewIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_review_resolves_known_values_and_requests_missing_profile_details(self):
        fields = [
            {"index": 0, "label": "Phone", "type": "tel", "required": True, "classification": "phone"},
            {"index": 1, "label": "Location (City)", "type": "text", "required": True, "classification": "city"},
            {"index": 2, "label": "How many years of Java development?", "type": "text", "required": True, "classification": "years_java"},
            {"index": 3, "label": "Current CTC?", "type": "text", "required": True, "classification": "current_ctc"},
            {"index": 4, "label": "Expected CTC?", "type": "text", "required": True, "classification": "expected_ctc"},
            {"index": 5, "label": "How soon can you join us?", "type": "text", "required": True, "classification": "join_availability"},
        ]
        profile = {
            "phone": "+91 9876543210",
            "city": "Greater Noida",
            "java_experience_years": "8",
            "current_ctc_lpa": "47",
            "ctc_currency": "INR",
        }
        result = await review_application_questions(fields, profile, {})

        self.assertEqual(result["supported_count"], 4)
        self.assertEqual(result["not_found_count"], 2)
        self.assertEqual(result["profile_update_required_count"], 2)
        by_index = {item["field_index"]: item for item in result["reviews"]}
        self.assertEqual(by_index[0]["suggested_answer"], "+91 9876543210")
        self.assertEqual(by_index[1]["suggested_answer"], "Greater Noida")
        self.assertEqual(by_index[2]["suggested_answer"], "8 years")
        self.assertEqual(by_index[3]["suggested_answer"], "INR 47 LPA")
        self.assertIn("expected_ctc_lpa", by_index[4]["profile_fields_needed"])
        self.assertIn("join_availability", by_index[5]["profile_fields_needed"])
        self.assertEqual({item["field_index"] for item in result["profile_update_requests"]}, {4, 5})


if __name__ == "__main__":
    unittest.main()
