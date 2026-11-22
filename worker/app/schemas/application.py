from pydantic import BaseModel, Field, HttpUrl


class PrepareApplicationRequest(BaseModel):
    application_id: str = Field(min_length=1, max_length=80)
    job_url: HttpUrl
    career_profile: dict = Field(min_length=1)
    tailored_resume_pdf_base64: str = Field(min_length=16)


class SubmitApplicationRequest(BaseModel):
    confirm_submit: bool
