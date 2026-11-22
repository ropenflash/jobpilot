# JobPilot

A human-in-the-loop job application copilot.

- Next.js dashboard
- Spring Boot control plane with MongoDB
- Python FastAPI worker
- OpenRouter for model inference
- Playwright browser automation is planned; this milestone does not submit applications.

**Safety boundary:** JobPilot prepares and reviews application data. No job application is submitted without explicit user confirmation in a later milestone. Never put credentials or secrets in prompts or source control.

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

export OPENROUTER_API_KEY="your-key"
export OPENROUTER_MODEL="openai/gpt-4o"
export OPENROUTER_MAX_TOKENS=3000
export OPENROUTER_SITE_URL="http://localhost:3000"
export OPENROUTER_SITE_NAME="JobPilot"

python -m uvicorn app.main:app --reload --port 8000
```
Worker: http://localhost:8000  
API docs: http://localhost:8000/docs

## 4. Start frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend: http://localhost:3000

## Environment
Copy `.env.example` to your local `.env` as a reference, but load the relevant variables into the worker process. The OpenRouter API key must remain on the Python worker and must never be exposed to the browser. Do not commit `.env`.

## Current API

### Spring Boot
- `GET /api/health` — backend and MongoDB health
- `POST /api/resumes` — upload a PDF resume
- `GET /api/profile` — load the saved career profile
- `PUT /api/profile` — save a reviewed career profile

### Python worker
- `GET /health` — worker health
- `GET /ai/status` — OpenRouter configuration status (does not return the key)
- `POST /ai/chat` — OpenRouter chat completion
- `POST /resume/parse` — extract structured career facts from a PDF
- `POST /jobs/analyze` — currently validates a job URL; Greenhouse extraction comes in Milestone 3

## Milestone 2: Resume intelligence
1. Open http://localhost:3000/profile.
2. Upload a text-based PDF resume (maximum 5 MB).
3. Spring Boot stores the PDF under `storage/resumes/` and calls the Python worker.
4. The worker extracts text with PyMuPDF and asks OpenRouter for structured career facts.
5. Spring Boot stores resume metadata and the extracted profile in MongoDB (`resumes` and `career_profiles`).
6. Review and correct the extracted facts, then explicitly save and verify the profile.

Scanned/image-only PDFs are not supported yet; OCR is a future enhancement. AI extraction is a draft and must be checked before relying on it.

## OpenRouter smoke test
```bash
curl -X POST http://localhost:8000/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with JobPilot AI is working"}]}'
```

## Security and limitations
- This is a local-development MVP, not production-hardened.
- Authentication, authorization, multi-user isolation, encryption at rest and retention controls are not yet implemented.
- Resumes contain personal information. Only upload files you are authorized to process.
- Keep `.env`, API keys, local virtual environments, build outputs and uploaded resumes out of Git.
