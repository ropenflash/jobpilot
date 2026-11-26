import unittest
from unittest.mock import AsyncMock, patch

from app.agents.application_workflow_agent import _heuristic_workflow, analyze_application_workflow
from app.services.vertex_client import VertexError


class ApplicationWorkflowAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_external_application_detected_from_instruction_and_contextual_link(self):
        page = {
            "rendered_text": "You must complete the Constellation application form instead. Use the provided link.",
            "instructions": ["Complete the external application form instead of this one."],
            "form_controls": [{
                "type": "select",
                "label": "Acknowledgement",
                "options": [{"text": "I understand I should use the provided link to the other form."}],
            }],
            "links": [{
                "text": "Constellation application",
                "href": "https://example.org/apply",
                "context": "Use this link to apply to the program.",
            }],
        }
        result = _heuristic_workflow(page)
        self.assertEqual(result["workflow_type"], "external_application")
        self.assertEqual(result["external_application_url"], "https://example.org/apply")

    def test_captcha_classification_has_priority(self):
        result = _heuristic_workflow({
            "rendered_text": "Verify you are human",
            "form_controls": [{"type": "text"}],
        })
        self.assertEqual(result["workflow_type"], "captcha_required")

    def test_conditional_and_multistep_classifications(self):
        conditional = _heuristic_workflow({
            "rendered_text": "If yes, please answer the following question.",
            "form_controls": [{"type": "text"}],
        })
        self.assertEqual(conditional["workflow_type"], "conditional_form")
        multistep = _heuristic_workflow({
            "rendered_text": "Step 1 of 3. Continue to next step.",
            "form_controls": [{"type": "text"}],
        })
        self.assertEqual(multistep["workflow_type"], "multi_step_form")

    @patch("app.agents.application_workflow_agent.generate_text", new_callable=AsyncMock)
    async def test_llm_external_url_is_rejected_if_not_present_in_evidence(self, generate):
        generate.return_value = """{"workflow_type":"external_application","confidence":0.99,
        "rationale":"external destination","external_application_url":"https://evil.example/app",
        "relevant_links":[],"required_actions":[],"stop_conditions":[],"signals":{}}"""
        result = await analyze_application_workflow({"links": []})
        self.assertIsNone(result["external_application_url"])
        self.assertEqual(result["analysis_source"], "llm")

    @patch("app.agents.application_workflow_agent.generate_text", new_callable=AsyncMock)
    async def test_vertex_failure_uses_heuristic_fallback(self, generate):
        generate.side_effect = VertexError("not configured")
        page = {
            "rendered_text": "Apply through the external application form.",
            "form_controls": [],
            "links": [{
                "text": "Application form",
                "href": "https://example.org/app",
                "context": "Apply through this form.",
            }],
        }
        result = await analyze_application_workflow(page)
        self.assertEqual(result["workflow_type"], "external_application")
        self.assertEqual(result["analysis_source"], "heuristic_fallback")


if __name__ == "__main__":
    unittest.main()
