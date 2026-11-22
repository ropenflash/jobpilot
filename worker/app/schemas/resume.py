from typing import Any

from pydantic import BaseModel, Field, field_validator


def _string_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return value


class ExperienceItem(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)

    @field_validator("technologies", mode="before")
    @classmethod
    def technologies_as_list(cls, value: Any) -> Any:
        return _string_list(value)


class EducationItem(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    graduation_year: str | None = None

    @field_validator("graduation_year", mode="before")
    @classmethod
    def year_as_text(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
        return value


class ProjectItem(BaseModel):
    name: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)

    @field_validator("technologies", mode="before")
    @classmethod
    def technologies_as_list(cls, value: Any) -> Any:
        return _string_list(value)


class ResumeProfile(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    professional_summary: str | None = None
    total_experience_years: float | str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    extraction_notes: list[str] = Field(default_factory=list)

    @field_validator("total_experience_years", mode="before")
    @classmethod
    def years_from_model(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            try:
                return float(text)
            except ValueError:
                return text
        return value

    @field_validator(
        "skills",
        "certifications",
        "extraction_notes",
        "experience",
        "education",
        "projects",
        mode="before",
    )
    @classmethod
    def lists_from_model(cls, value: Any) -> Any:
        if value is None:
            return []
        return value if value.__class__.__name__ != "str" else _string_list(value)
