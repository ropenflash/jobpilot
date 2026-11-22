# JobPilot

A human-in-the-loop job application copilot.

## Stack
- Next.js frontend
- Spring Boot + MongoDB control plane
- Python FastAPI worker
- OpenRouter for model inference

## Local prerequisites
- Docker Desktop
- Java 21 and Maven 3.9+
- Python 3.11+
- Node.js 20+

## Start services

### MongoDB
```bash
docker compose up -d
```

### Spring Boot
```bash
cd backend
mvn spring-boot:run
```

### Python worker
```bash
cd worker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENROUTER_API_KEY="your-key"
export OPENROUTER_MODEL="openai/gpt-4o"
export OPENROUTER_MAX_TOKENS=3000
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. API docs: http://localhost:8000/docs.

## Milestone 2: Resume intelligence
1. Open http://localhost:3000/profile.
2. Upload a text-based PDF resume (maximum 5 MB).
3. The backend stores the PDF locally and calls the Python worker.
4. The worker extracts text with PyMuPDF and asks OpenRouter to produce structured career facts.
5. The backend stores resume metadata and the extracted career profile in MongoDB.
6. Review every field and select **Save and verify profile**.

Endpoints:
- `POST /api/resumes` — multipart PDF upload
- `GET /api/profile` — load extracted career profile
- `PUT /api/profile` — save reviewed profile as verified
- `POST /resume/parse` — worker PDF extraction
- `POST /ai/chat` — OpenRouter chat completion
- `GET /ai/status` — OpenRouter configuration status

Scanned/image-only PDFs are not supported yet. OCR is planned separately. AI extraction is a draft: verify facts before relying on them.

## Safety and limitations
- This MVP does not submit job applications.
- Keep API keys in local environment variables; never commit `.env`.
- Resumes contain personal information. This MVP is intended for local development and is not yet production-hardened with authentication, encryption at rest, retention controls, or multi-user isolation.
- Only upload resumes you are authorized to process.
