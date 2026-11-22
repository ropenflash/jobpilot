from datetime import datetime, timezone
import json
import os
from urllib.parse import urlparse

import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl

from app.schemas.resume import ResumeProfile
from app.services.openrouter_client import OpenRouterError, chat_completion

app = FastAPI(
    title="JobPilot Worker",
    version="0.3.0",
    description="AI and browser worker using OpenRouter."
)


class AnalyzeJobRequest(BaseModel):
    url: HttpUrl


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
        "provider": "openrouter",
        "configured": bool(os.getenv("OPENROUTER_API_KEY")),
        "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o"),
    }


@app.post("/ai/chat")
async def ai_chat(request: ChatRequest):
    try:
        return await chat_completion(
            [message.model_dump() for message in request.messages],
            request.model,
        )
    except OpenRouterError as exc:
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
        result = await chat_completion(
            [
                {
                    "role": "system",
                    "content": "You extract career facts carefully. Never fabricate information.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw = result["choices"][0]["message"]["content"]
        parsed = json.loads(raw)
        return ResumeProfile.model_validate(parsed)
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="The model returned an invalid profile. Please retry.",
        ) from exc


@app.post("/jobs/analyze")
async def analyze_job(request: AnalyzeJobRequest):
    parsed = urlparse(str(request.url))
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only HTTP(S) URLs are supported.")
    return {
        "status": "RECEIVED",
        "portal": "GREENHOUSE" if parsed.hostname and "greenhouse.io" in parsed.hostname else "UNKNOWN",
        "url": str(request.url),
        "message": "URL validated. Greenhouse extraction will be added in Milestone 3.",
    }
