from pydantic import BaseModel, Field, HttpUrl


class PrepareApplicationRequest(BaseModel):
    application_id: str = Field(min_length=1, max_length=80)
    job_url: HttpUrl
    career_profile: dict = Field(min_length=1)
    tailored_resume_base64: str = Field(min_length=16)
    tailored_resume_filename: str = Field(default="tailored-resume.pdf", min_length=1, max_length=160)
    tailored_resume: dict = Field(default_factory=dict)
    job_context: dict = Field(default_factory=dict)


class RefreshApplicationRequest(BaseModel):
    career_profile: dict | None = None
    tailored_resume: dict | None = None
    manual_answer: dict | None = None
    job_context: dict | None = None


class SubmitApplicationRequest(BaseModel):
    confirm_submit: bool
