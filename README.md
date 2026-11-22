# JobPilot

A human-in-the-loop job application copilot. Milestone 1 provides a runnable local foundation:
- Next.js dashboard
- Spring Boot API with MongoDB connectivity and health endpoint
- Python FastAPI worker with health and job-analysis placeholder endpoints
- MongoDB via Docker Compose

**Safety boundary:** this milestone does not submit applications or automate websites. Browser automation and approval-gated submission are later milestones. Never put credentials or secrets in prompts or source control.

## Prerequisites
- Docker Desktop
- Java 21
- Maven 3.9+
- Python 3.11+
- Node.js 20+

## 1. Start MongoDB
```bash
docker compose up -d
```

## 2. Start backend
```bash
cd backend
mvn spring-boot:run
```
Backend: http://localhost:8080  
Health: http://localhost:8080/api/health

## 3. Start worker
```bash
cd worker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Worker: http://localhost:8000  
Docs: http://localhost:8000/docs

## 4. Start frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend: http://localhost:3000

## Environment
Copy `.env.example` to `.env` and configure values as needed. The worker uses OpenRouter for chat completions. Copy `.env.example` to `.env`, set
`OPENROUTER_API_KEY`, and export the variables in the worker shell (or load `.env`
with your preferred environment loader). The default model is `openai/gpt-4o`.
The API key stays on the Python worker and must never be sent to the browser.

## Current API
- `GET /api/health` — backend + MongoDB connectivity
- `GET /api/profile` — returns an empty profile placeholder
- `GET /api/jobs` — returns an empty job list
- `GET /health` — worker health
- `POST /jobs/analyze` — validates a URL and returns a placeholder response
- `GET /ai/status` — reports whether OpenRouter is configured (never returns the key)
- `POST /ai/chat` — sends chat messages to OpenRouter

## Milestone 1 scope
This is starter code, not a production deployment. Authentication, authorization, resume upload, job parsing, LLM calls, browser sessions, approval, and submission are intentionally not implemented yet. Do not use it to submit real applications.


## OpenRouter smoke test
Set the worker environment:
```bash
export OPENROUTER_API_KEY="your-key"
export OPENROUTER_MODEL="openai/gpt-4o"
export OPENROUTER_SITE_URL="http://localhost:3000"
export OPENROUTER_SITE_NAME="JobPilot"
```
Then call:
```bash
curl -X POST http://localhost:8000/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is the meaning of life?"}]}'
```
Do not commit `.env` or paste API keys into source files, frontend code, screenshots, or chat.
