from typing import Any

from pydantic import BaseModel, Field, field_validator


class TailoredBulletDraft(BaseModel):
    text: str = Field(min_length=8, max_length=500)
    source_refs: list[str] = Field(min_length=1)


class TailoredExperienceDraft(BaseModel):
    source_index: int = Field(ge=0)
    bullets: list[TailoredBulletDraft] = Field(min_length=1, max_length=6)


class TailoredProjectDraft(BaseModel):
    source_index: int = Field(ge=0)
    bullets: list[TailoredBulletDraft] = Field(min_length=1, max_length=4)


class ResumeChangeDraft(BaseModel):
    section: str
    change: str
    rationale: str
    source_refs: list[str] = Field(default_factory=list)


class TailoredResumeDraft(BaseModel):
    target_headline: str = Field(min_length=2, max_length=120)
    professional_summary: str = Field(min_length=30, max_length=1200)
    summary_source_refs: list[str] = Field(min_length=1)
    selected_skills: list[str] = Field(default_factory=list, max_length=40)
    experience: list[TailoredExperienceDraft] = Field(default_factory=list)
    projects: list[TailoredProjectDraft] = Field(default_factory=list)
    change_log: list[ResumeChangeDraft] = Field(default_factory=list)

    @field_validator("selected_skills", mode="before")
    @classmethod
    def skills_to_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class TailoredResumeRequest(BaseModel):
    job: dict
    requirements: dict
    match: dict = Field(default_factory=dict)
    career_profile: dict
    style: str = Field(default="classic", pattern="^(classic|modern|compact)$")
