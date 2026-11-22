import unittest

from fastapi import HTTPException

from app.agents.resume_tailor import (
    _build_source_map,
    _make_docx,
    _make_pdf,
    _style_config,
    _validated_content,
)
from app.schemas.tailored_resume import (
    ResumeChangeDraft,
    TailoredBulletDraft,
    TailoredExperienceDraft,
    TailoredProjectDraft,
    TailoredResumeDraft,
)


class ResumeTailoringTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "full_name": "Test Candidate",
            "email": "candidate@example.com",
            "phone": "+91 9000000000",
            "location": "India",
            "headline": "Application Architect",
            "professional_summary": "Backend engineer with Java and cloud experience.",
            "skills": ["Java", "Spring Boot", "MongoDB"],
            "experience": [
                {
                    "company": "Example Co",
                    "title": "Application Architect",
                    "location": "India",
                    "start_date": "2020",
                    "end_date": "Present",
                    "description": "Designed Java microservices and led backend architecture decisions.",
                    "technologies": ["Java", "Spring Boot", "MongoDB"],
                }
            ],
            "projects": [
                {
                    "name": "Agent platform",
                    "description": "Built an agent orchestration platform with a worker model.",
                    "technologies": ["Python", "Kafka"],
                }
            ],
            "education": [{"degree": "B.Tech", "institution": "Example University", "graduation_year": "2014"}],
            "certifications": ["Cloud Certification"],
        }
        self.job = {"title": "Staff Backend Engineer", "company": "Hiring Co"}
        self.source_map, self.allowed_skills = _build_source_map(self.profile)

    def _draft(self):
        return TailoredResumeDraft(
            target_headline="Backend Architecture and Platform Engineering",
            professional_summary=(
                "Application architect with experience designing Java microservices "
                "and leading backend architecture decisions."
            ),
            summary_source_refs=["experience:0", "profile:headline"],
            selected_skills=["Java", "Spring Boot", "MongoDB", "Invented Technology"],
            experience=[
                TailoredExperienceDraft(
                    source_index=0,
                    bullets=[
                        TailoredBulletDraft(
                            text="Designed Java microservices and led backend architecture decisions.",
                            source_refs=["experience:0", "skill:0"],
                        )
                    ],
                )
            ],
            projects=[
                TailoredProjectDraft(
                    source_index=0,
                    bullets=[
                        TailoredBulletDraft(
                            text="Built an agent orchestration platform using a worker model.",
                            source_refs=["project:0"],
                        )
                    ],
                )
            ],
            change_log=[
                ResumeChangeDraft(
                    section="Summary",
                    change="Emphasized platform and architecture experience.",
                    rationale="Highlights evidence relevant to the target role.",
                    source_refs=["experience:0"],
                )
            ],
        )

    def test_source_map_contains_only_profile_evidence_refs(self):
        self.assertIn("experience:0", self.source_map)
        self.assertIn("project:0", self.source_map)
        self.assertIn("skill:0", self.source_map)
        self.assertNotIn("email", self.source_map)

    def test_copy_employer_role_dates_education_and_certifications_from_source(self):
        resume = _validated_content(
            self._draft(), self.profile, self.job, self.source_map, self.allowed_skills
        )
        role = resume["experience"][0]
        self.assertEqual(role["company"], "Example Co")
        self.assertEqual(role["title"], "Application Architect")
        self.assertEqual(role["start_date"], "2020")
        self.assertEqual(role["end_date"], "Present")
        self.assertEqual(resume["education"], self.profile["education"])
        self.assertEqual(resume["certifications"], self.profile["certifications"])
        self.assertNotIn("Invented Technology", resume["skills"])

    def test_rejects_bullet_without_matching_source_reference(self):
        draft = self._draft()
        draft.experience[0].bullets[0].source_refs = ["skill:0"]
        with self.assertRaises(HTTPException):
            _validated_content(draft, self.profile, self.job, self.source_map, self.allowed_skills)

    def test_each_supported_style_generates_both_document_formats(self):
        resume = _validated_content(
            self._draft(), self.profile, self.job, self.source_map, self.allowed_skills
        )
        for style in ("classic", "modern", "compact"):
            with self.subTest(style=style):
                docx = _make_docx(resume, style)
                pdf = _make_pdf(resume, style)
                self.assertTrue(docx.startswith(b"PK"))
                self.assertTrue(pdf.startswith(b"%PDF"))

    def test_unknown_resume_style_is_rejected(self):
        with self.assertRaises(HTTPException):
            _style_config("creative")


if __name__ == "__main__":
    unittest.main()
