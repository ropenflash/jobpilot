import unittest

from app.agents.application_answer_decision import decide_application_answer


class ApplicationAnswerDecisionTests(unittest.TestCase):
    def _field(self, **overrides):
        value = {
            "index": 2,
            "label": "Email",
            "classification": "email",
            "type": "email",
            "filled": False,
        }
        value.update(overrides)
        return value

    def test_verified_profile_answer_is_allowed_when_supported_and_control_compatible(self):
        decision = decide_application_answer(
            self._field(),
            "person@example.com",
            "verified_profile",
            {"email": "person@example.com"},
            {"resume": {"contact": {"email": "person@example.com"}}},
        )
        self.assertEqual(decision["action"], "autofill")
        self.assertEqual(decision["answer"], "person@example.com")
        self.assertEqual(decision["evidence"][0]["source"], "verified_profile")

    def test_explicit_profile_resume_conflict_blocks_autofill(self):
        decision = decide_application_answer(
            self._field(),
            "person@example.com",
            "verified_profile",
            {"email": "person@example.com"},
            {"resume": {"contact": {"email": "other@example.com"}}},
        )
        self.assertEqual(decision["action"], "manual_review")
        self.assertTrue(decision["conflicts"])
        self.assertIn("conflicting", decision["reason"])

    def test_untraceable_profile_candidate_is_not_accepted(self):
        decision = decide_application_answer(
            self._field(),
            "person@example.com",
            "verified_profile",
            {"full_name": "Person Example"},
            {},
        )
        self.assertEqual(decision["action"], "manual_review")
        self.assertIsNone(decision["answer"])

    def test_candidate_confirmed_saved_answer_can_be_reused(self):
        profile = {
            "application_answers": [{
                "question": "Why this role?",
                "answer": "The product and engineering challenges interest me.",
                "candidate_confirmed": True,
            }]
        }
        decision = decide_application_answer(
            self._field(label="Why this role?", classification="manual", type="textarea"),
            "The product and engineering challenges interest me.",
            "saved_application_answer",
            profile,
            {},
        )
        self.assertEqual(decision["action"], "autofill")
        self.assertEqual(decision["answer_source"], "saved_application_answer")

    def test_unconfirmed_saved_answer_is_rejected(self):
        profile = {
            "application_answers": [{
                "question": "Why this role?",
                "answer": "The product is interesting.",
                "candidate_confirmed": False,
            }]
        }
        decision = decide_application_answer(
            self._field(label="Why this role?", classification="manual", type="textarea"),
            "The product is interesting.",
            "saved_application_answer",
            profile,
            {},
        )
        self.assertEqual(decision["action"], "manual_review")

    def test_checkbox_and_sensitive_fields_always_require_manual_review(self):
        for field in (
            self._field(label="I agree to the privacy policy", classification="checkbox_review", type="checkbox"),
            self._field(label="Are you legally authorised to work?", classification="sensitive_or_eligibility"),
        ):
            decision = decide_application_answer(
                field, "Yes", "verified_profile", {"email": "person@example.com"}, {}
            )
            self.assertEqual(decision["action"], "manual_review")

    def test_select_requires_a_unique_exact_or_supported_range_option(self):
        profile = {"java_experience_years": 8}
        field = self._field(label="Years of Java experience", classification="years_java", type="select")
        decision = decide_application_answer(
            field, "8 years", "verified_profile", profile, {},
            [{"value": "a", "text": "5-10 years"}, {"value": "b", "text": "10+ years"}],
        )
        self.assertEqual(decision["action"], "autofill")
        self.assertEqual(decision["option"]["value"], "a")

        ambiguous = decide_application_answer(
            field, "8 years", "verified_profile", profile, {},
            [{"value": "a", "text": "5-10 years"}, {"value": "b", "text": "6-9 years"}],
        )
        self.assertEqual(ambiguous["action"], "manual_review")

    def test_invalid_email_and_out_of_range_number_are_blocked(self):
        bad_email = decide_application_answer(
            self._field(), "not-an-email", "verified_profile",
            {"email": "not-an-email"}, {},
        )
        self.assertEqual(bad_email["action"], "manual_review")

        number = decide_application_answer(
            self._field(label="Years of experience", classification="experience_range", type="number", min="0", max="20"),
            "24 years", "verified_profile", {"total_experience_years": 24}, {},
        )
        self.assertEqual(number["action"], "manual_review")


    def test_candidate_supported_ai_draft_stays_review_only(self):
        decision = decide_application_answer(
            self._field(label="Why this role?", classification="manual", type="textarea"),
            "An evidence-backed draft.",
            "ai_draft",
            {"application_answers": []},
            {},
        )
        self.assertEqual(decision["action"], "candidate_confirmation")
        self.assertIsNone(decision["answer"])

    def test_combined_spring_and_microservices_tenure_does_not_create_false_conflicts(self):
        profile = {
            "spring_boot_experience_years": 6,
            "microservices_experience_years": 5,
        }
        resume = {
            "resume": {
                "spring_boot_experience_years": 6,
                "microservices_experience_years": 5,
            }
        }
        decision = decide_application_answer(
            self._field(
                label="Spring Boot and microservices experience",
                classification="years_spring_boot_microservices",
                type="text",
            ),
            "Spring Boot: 6 years; Microservices: 5 years",
            "verified_profile",
            profile,
            resume,
        )
        self.assertEqual(decision["action"], "autofill")

    def test_phone_country_code_must_be_supported_by_verified_phone_number(self):
        field = self._field(label="Country code", classification="phone_country_code", type="select")
        decision = decide_application_answer(
            field, "+91", "verified_profile",
            {"phone": "+91 9876543210"}, {},
            [{"value": "+91", "text": "+91"}],
        )
        self.assertEqual(decision["action"], "autofill")
        self.assertEqual(decision["answer"], "+91")

    def test_not_serving_notice_can_support_conditional_lwd_answer(self):
        decision = decide_application_answer(
            self._field(label="Last working day", classification="last_working_day", type="text"),
            "Not currently serving notice.",
            "verified_profile",
            {"currently_serving_notice": "no"},
            {},
        )
        self.assertEqual(decision["action"], "autofill")

    def test_invalid_date_and_url_are_not_filled(self):
        date_decision = decide_application_answer(
            self._field(label="Last working day", classification="last_working_day", type="date"),
            "Next month", "verified_profile", {"official_last_working_day": "Next month"}, {},
        )
        self.assertEqual(date_decision["action"], "manual_review")

        url_decision = decide_application_answer(
            self._field(label="Website", classification="website", type="url"),
            "not a url", "verified_profile", {"website": "not a url"}, {},
        )
        self.assertEqual(url_decision["action"], "manual_review")


if __name__ == "__main__":
    unittest.main()
