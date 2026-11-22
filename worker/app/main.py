from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl, Field
from urllib.parse import urlparse
from datetime import datetime, timezone

from app.services.openrouter_client import chat_completion, OpenRouterError

app = FastAPI(
    title="JobPilot Worker",
    version="0.2.0",
    description="AI and browser worker using OpenRouter for model calls."
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
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/ai/status")
async def ai_status():
    import os
    return {
        "provider": "openrouter",
        "configured": bool(os.getenv("OPENROUTER_API_KEY")),
        "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
    }

@app.post("/ai/chat")
async def ai_chat(request: ChatRequest):
    try:
        result = await chat_completion(
            [message.model_dump() for message in request.messages],
            request.model,
        )
        return result
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@app.post("/jobs/analyze")
async def analyze_job(request: AnalyzeJobRequest):
    parsed = urlparse(str(request.url))
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only HTTP(S) URLs are supported.")

    # Milestone 1 deliberately validates but does not fetch arbitrary URLs.
    # Milestone 3 will add controlled Greenhouse extraction and LLM analysis.
    return {
        "status": "RECEIVED",
        "portal": "GREENHOUSE" if parsed.hostname and "greenhouse.io" in parsed.hostname else "UNKNOWN",
        "url": str(request.url),
        "message": "URL validated. Greenhouse extraction will be added in Milestone 3."
    }
