from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _as_string_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return value


class GreenhouseJob(BaseModel):
    job_id: int
    board_token: str
    title: str
    company: str
    location: str | None = None
    job_url: str
    description: str
    updated_at: str | None = None


class JobRequirements(BaseModel):
    summary: str
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    minimum_experience_years: float | None = None
    maximum_experience_years: float | None = None
    employment_type: str | None = None
    salary_range: str | None = None

    @field_validator("responsibilities", "required_skills", "preferred_skills", "qualifications", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> Any:
        return _as_string_list(value)


class MatchEvidence(BaseModel):
    category: Literal[
        "required_skill",
        "experience_responsibilities",
        "project_evidence",
        "preferred_skill",
    ]
    requirement: str
    profile_evidence: str
    assessment: Literal["matched", "partial", "not_evidenced"]


class ScoreBreakdown(BaseModel):
    category: str
    weight_percentage: int
    category_score: int
    evidence_count: int


class JobMatch(BaseModel):
    score: int = Field(ge=0, le=100)
    recommendation: Literal["strong_match", "possible_match", "weak_match"]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    evidence: list[MatchEvidence] = Field(default_factory=list)
    score_breakdown: list[ScoreBreakdown] = Field(default_factory=list)
    rationale: str

    @field_validator("strengths", "gaps", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> Any:
        return _as_string_list(value)


class VisualInspection(BaseModel):
    status: Literal["completed", "unavailable", "disabled"] = "unavailable"
    screenshots_captured: int = Field(default=0, ge=0, le=5)
    page_title: str | None = None
    page_headings: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("page_headings", "findings", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> Any:
        return _as_string_list(value)


class JobAnalysisResponse(BaseModel):
    job: GreenhouseJob
    requirements: JobRequirements
    match: JobMatch
    visual_inspection: VisualInspection = Field(default_factory=VisualInspection)
