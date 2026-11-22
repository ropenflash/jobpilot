import base64
import unittest

import fitz

from app.agents.application_answer_rag import (
    extract_original_resume_text,
    sanitize_original_resume_text,
)
from app.agents.application_question_reviewer import build_evidence
from app.agents.application_answer_rag import retrieve_question_evidence


class OriginalResumeEvidenceTests(unittest.TestCase):
    def test_sanitizer_removes_contact_compensation_urls_and_candidate_name(self):
        source = """
        Candidate Example | Senior Backend Engineer
        candidate@example.com | +91 98765 43210
        LinkedIn: https://linkedin.com/in/candidate
        Current CTC: INR 47 LPA
        Built Java services and Kafka event pipelines for order processing.
        Led production reliability improvements and reduced incident rates.
        """
        sanitized = sanitize_original_resume_text(
            source,
            {"full_name": "Candidate Example"},
        )

        self.assertNotIn("Candidate Example", sanitized)
        self.assertNotIn("candidate@example.com", sanitized)
        self.assertNotIn("98765", sanitized)
        self.assertNotIn("linkedin.com", sanitized)
        self.assertNotIn("47 LPA", sanitized)
        self.assertIn("Built Java services and Kafka event pipelines", sanitized)
        self.assertIn("production reliability improvements", sanitized)

    def test_extract_original_resume_text_reads_pdf_in_memory_and_sanitizes(self):
        document = fitz.open()
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "Candidate Example\ncandidate@example.com\n"
            "Designed Kafka consumers for distributed event processing.",
        )
        pdf_bytes = document.tobytes()
        document.close()

        extracted = extract_original_resume_text(
            base64.b64encode(pdf_bytes).decode("ascii"),
            {"full_name": "Candidate Example"},
        )
        self.assertNotIn("Candidate Example", extracted)
        self.assertNotIn("candidate@example.com", extracted)
        self.assertIn("Designed Kafka consumers for distributed event processing.", extracted)

    def test_invalid_or_oversized_source_pdf_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_original_resume_text(base64.b64encode(b"not a pdf").decode("ascii"))

        with self.assertRaises(ValueError):
            extract_original_resume_text(base64.b64encode(b"%PDF" + b"x" * (5 * 1024 * 1024)).decode("ascii"))

    def test_original_pdf_text_is_chunked_with_traceable_source_paths(self):
        evidence = build_evidence(
            {"skills": ["Java"]},
            {"summary": "Backend engineer."},
        )
        from app.agents.application_question_reviewer import _flatten_evidence
        original = []
        _flatten_evidence(
            "Kafka " * 500,
            "original_resume",
            "pdf_text",
            original,
        )
        combined = evidence + original
        self.assertTrue(any(item["source"] == "original_resume" for item in combined))
        self.assertTrue(all(item["id"].startswith("original_resume:pdf_text") for item in original))

    def test_original_pdf_evidence_is_retrievable_by_question(self):
        evidence = [{
            "id": "original_resume:pdf_text",
            "source": "original_resume",
            "path": "pdf_text",
            "text": "Designed Kafka consumers and event pipelines for distributed order processing.",
        }]
        result = retrieve_question_evidence(
            {"question": "Describe your experience with Kafka event pipelines.", "classification": "manual"},
            evidence,
        )
        self.assertEqual(result["retrieved_count"], 1)
        self.assertEqual(result["items"][0]["source"], "original_resume")


if __name__ == "__main__":
    unittest.main()
