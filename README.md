# JobPilot

A human-in-the-loop job application copilot.

- Next.js dashboard
- Spring Boot control plane with MongoDB
- Python FastAPI worker
- Gemini on Vertex AI for model inference
- Greenhouse Job Board API for public job-post retrieval
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

gcloud auth application-default login
export GCP_PROJECT="agentos-514612"
export GCP_LOCATION="global"
export VERTEX_MODEL="gemini-3.8-flash"
export VERTEX_MAX_TOKENS=3000
export VERTEX_JOB_MAX_OUTPUT_TOKENS=4096

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
Copy `.env.example` to your local `.env`. The worker loads that file on startup. Vertex calls use Application Default Credentials from `gcloud auth application-default login`; do not put a service-account key in the repo. Do not commit `.env`.

## Current API

### Spring Boot
- `GET /api/health` — backend and MongoDB health
- `POST /api/resumes` — upload a PDF resume
- `GET /api/profile` — load the saved career profile
- `PUT /api/profile` — save a reviewed career profile
- `POST /api/jobs/analyze` — analyze a public Greenhouse job against the verified profile
- `GET /api/jobs` — list the latest 50 saved job analyses
- `GET /api/jobs/{id}` — retrieve a saved job analysis

### Python worker
- `GET /health` — worker health
- `GET /ai/status` — Vertex project, location, and model
- `POST /ai/chat` — Gemini chat completion on Vertex AI
- `POST /resume/parse` — extract structured career facts from a PDF
- `POST /jobs/analyze` — retrieve a public Greenhouse posting, extract requirements and match evidence

## Milestone 2: Resume intelligence
1. Open http://localhost:3000/profile.
2. Upload a text-based PDF resume (maximum 5 MB).
3. Spring Boot stores the PDF under `storage/resumes/` and calls the Python worker.
4. The worker extracts text with PyMuPDF and asks Gemini on Vertex AI for structured career facts.
5. Spring Boot stores resume metadata and the extracted profile in MongoDB (`resumes` and `career_profiles`).
6. Review and correct the extracted facts, then explicitly save and verify the profile.

Scanned/image-only PDFs are not supported yet; OCR is a future enhancement. AI extraction is a draft and must be checked before relying on it.

## Milestone 3: Greenhouse job intelligence
1. Verify your saved career profile at http://localhost:3000/profile.
2. Open http://localhost:3000/jobs.
3. Paste a public job URL with this format: `https://boards.greenhouse.io/{board_token}/jobs/{job_id}`. The alternate `job-boards.greenhouse.io` host is also accepted.
4. Spring Boot checks that the verified career profile exists and sends the URL plus profile facts (excluding contact identifiers) to the Python worker.
5. The worker validates the exact Greenhouse host and URL path, then calls the public Greenhouse Job Board API with `content=true`.
6. The worker converts the returned HTML description into plain text and asks Gemini to extract role requirements and compare them with the career profile.
7. The worker returns requirement-level evidence. The application calculates a deterministic score: required skills 40%, experience/responsibilities 30%, project evidence 20%, and preferred skills 10%. Categories absent from the comparison are excluded and the remaining weights are normalized to total 100%.
8. Spring Boot saves the job, requirements, score and evidence in MongoDB's `jobs` collection. The same Greenhouse board token and job ID update the existing record rather than creating duplicates.
9. Review the score breakdown, matched evidence and gaps in the Jobs page. The score is a profile-evidence estimate, not a prediction of hiring success.

### Supported URLs and limitations
- Only public Greenhouse job postings on `boards.greenhouse.io` and `job-boards.greenhouse.io` are supported.
- URL validation uses an exact hostname allow-list; the worker does not fetch arbitrary user-supplied hosts.
- The job must still be publicly available through the Greenhouse Job Board API.
- Company name is not present in every public Greenhouse job payload; in that case the board token is used as a display fallback.
- Job analysis does not tailor a resume, open a browser, fill an application, or submit anything.
- AI output can be incomplete. Confirm the job description and evidence before using the analysis to make decisions.

## Vertex smoke test
```bash
curl -X POST http://localhost:8000/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with JobPilot AI is working"}]}'
```

## Test job retrieval and analysis
```bash
curl -X POST http://localhost:8080/api/jobs/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"}'
```
Replace the example URL with a currently published public Greenhouse posting.

## Worker unit tests
From the `worker` directory, with the worker dependencies installed:
```bash
python -m unittest discover -s tests -v
```

## Security and limitations
- This is a local-development MVP, not production-hardened.
- Authentication, authorization, multi-user isolation, encryption at rest and retention controls are not yet implemented.
- Resumes contain personal information. Only upload files you are authorized to process.
- Keep `.env`, API keys, local virtual environments, build outputs and uploaded resumes out of Git.
