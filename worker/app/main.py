from datetime import datetime, timezone
import json
import logging
from pathlib import Path

import fitz
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl, ValidationError

from app.agents.job_analyzer import analyze_and_match
from app.agents.resume_tailor import tailor_resume
from app.browser.application_manager import ApplicationAutomationError, application_sessions
from app.schemas.job import JobAnalysisResponse
from app.schemas.resume import ResumeProfile
from app.schemas.tailored_resume import TailoredResumeRequest
from app.schemas.application import (
    PrepareApplicationRequest,
    RefreshApplicationRequest,
    SubmitApplicationRequest,
)
from app.services.greenhouse import fetch_greenhouse_job
from app.services.job_page_inspector import inspect_greenhouse_job_page
from app.services.vertex_client import (
    VertexError,
    credentials_available,
    generate_text,
    location,
    model_name,
    project_id,
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="JobPilot Worker",
    version="0.6.0",
    description="AI resume intelligence and human-in-the-loop Greenhouse job and application analysis."
)


class AnalyzeJobRequest(BaseModel):
    url: HttpUrl
    career_profile: dict = Field(min_length=1)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    model: str | None = None


@app.get("/health")
async def health():
    return {
        "service": "jobpilot-worker",
        "status": "UP",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ai/status")
async def ai_status():
    return {
        "provider": "vertex",
        "configured": credentials_available(),
        "project": project_id(),
        "location": location(),
        "model": model_name(),
    }


@app.post("/ai/chat")
async def ai_chat(request: ChatRequest):
    try:
        content = await generate_text(
            [message.model_dump() for message in request.messages],
            request.model,
        )
        return {"provider": "vertex", "model": request.model or model_name(), "content": content}
    except VertexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/resume/parse", response_model=ResumeProfile)
async def parse_resume(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Please upload a PDF resume.")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller.")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF.")

    try:
        with fitz.open(stream=content, filetype="pdf") as pdf:
            resume_text = "\n".join(page.get_text() for page in pdf)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not read this PDF.") from exc

    if len(resume_text.strip()) < 80:
        raise HTTPException(
            status_code=422,
            detail="Very little text was found. This may be a scanned PDF; OCR is not included yet.",
        )

    prompt = (
        "Extract a factual career profile from this resume. Return ONLY valid JSON. "
        "Never infer or invent details. Use null for unknown scalar fields and empty arrays "
        "for unknown lists. Preserve ambiguous dates as written and add an extraction note. "
        "Do not infer protected or sensitive personal attributes. "
        "Expected keys: full_name, email, phone, location, headline, professional_summary, "
        "total_experience_years, skills, experience (company,title,location,start_date,end_date,"
        "description,technologies), education (institution,degree,field_of_study,graduation_year), "
        "projects (name,description,technologies), certifications, extraction_notes.\n\n"
        "RESUME TEXT:\n" + resume_text[:24000]
    )

    try:
        raw = await generate_text(
            [
                {
                    "role": "system",
                    "content": "You extract career facts carefully. Never fabricate information.",
                },
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
        )
        parsed = json.loads(raw)
        return ResumeProfile.model_validate(parsed)
    except VertexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail="The model did not return JSON. Please retry.",
        ) from exc
    except ValidationError as exc:
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
        raise HTTPException(
            status_code=502,
            detail=f"The model returned a profile that does not match the expected fields: {fields}.",
        ) from exc


@app.post("/jobs/analyze", response_model=JobAnalysisResponse)
async def analyze_job(request: AnalyzeJobRequest):
    job_data = await fetch_greenhouse_job(str(request.url))
    try:
        page_inspection = await inspect_greenhouse_job_page(str(request.url))
    except Exception:
        logger.warning(
            "Visual inspection failed for Greenhouse job URL; continuing with API text only.",
            exc_info=True,
        )
        page_inspection = {
            "status": "unavailable",
            "screenshots": [],
            "page_title": None,
            "page_headings": [],
            "rendered_text": "",
            "note": (
                "Visual inspection was unavailable. The job was analyzed using the Greenhouse "
                "API description only. Install Chromium with python -m playwright install chromium "
                "to enable screenshots."
            ),
        }
    return await analyze_and_match(job_data, request.career_profile, page_inspection)


@app.post("/resumes/tailor")
async def tailor_resume_endpoint(request: TailoredResumeRequest):
    return await tailor_resume(
        job=request.job,
        requirements=request.requirements,
        match=request.match,
        profile=request.career_profile,
        style=request.style,
    )

def _application_error(exc: ApplicationAutomationError):
    return HTTPException(status_code=409, detail=str(exc))


@app.post("/applications/prepare")
async def prepare_application(request: PrepareApplicationRequest):
    try:
        return await application_sessions.prepare(
            application_id=request.application_id,
            job_url=str(request.job_url),
            career_profile=request.career_profile,
            resume_base64=request.tailored_resume_base64,
            resume_filename=request.tailored_resume_filename,
            tailored_resume=request.tailored_resume,
            job_context=request.job_context,
            source_resume_base64=request.source_resume_base64,
        )
    except ApplicationAutomationError as exc:
        raise _application_error(exc) from exc
    except Exception as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or ("browser" in message.lower() and "launch" in message.lower()):
            message = "Chromium is not installed or could not launch. Run playwright install chromium on this computer."
        raise HTTPException(status_code=502, detail=message) from exc


@app.get("/applications/{session_id}")
async def get_application(session_id: str):
    try:
        return await application_sessions.get(session_id)
    except ApplicationAutomationError as exc:
        raise _application_error(exc) from exc


@app.post("/applications/{session_id}/refresh")
async def refresh_application(
    session_id: str,
    request: RefreshApplicationRequest | None = None,
):
    try:
        return await application_sessions.refresh(
            session_id,
            career_profile=request.career_profile if request else None,
            tailored_resume=request.tailored_resume if request else None,
            manual_answer=request.manual_answer if request else None,
            job_context=request.job_context if request else None,
        )
    except ApplicationAutomationError as exc:
        raise _application_error(exc) from exc


@app.post("/applications/{session_id}/submit")
async def submit_application(session_id: str, request: SubmitApplicationRequest):
    try:
        return await application_sessions.submit(session_id, request.confirm_submit)
    except ApplicationAutomationError as exc:
        raise _application_error(exc) from exc


@app.post("/applications/{session_id}/cancel")
async def cancel_application(session_id: str):
    try:
        return await application_sessions.cancel(session_id)
    except ApplicationAutomationError as exc:
        raise _application_error(exc) from exc
