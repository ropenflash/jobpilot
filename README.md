# JobPilot

A human-in-the-loop job application copilot.

- Next.js dashboard
- Spring Boot control plane with MongoDB
- Python FastAPI worker
- Gemini on Vertex AI for model inference
- Greenhouse Job Board API for public job-post retrieval
- DOCX/PDF resume generation for job-specific tailoring
- Playwright headless browser inspection of rendered Greenhouse job pages, plus human-in-the-loop application automation.

**Safety boundary:** JobPilot prepares and reviews application materials. No job application is submitted without explicit user confirmation in a later milestone. Never put credentials or secrets in prompts or source control.

## Prerequisites
- Docker Desktop
- Java 21
- Maven 3.9+
- Python 3.11+
- Node.js 20+

## 1. Start MongoDB
\`\`\`bash
docker compose up -d
\`\`\`

## 2. Start backend
\`\`\`bash
cd backend
mvn spring-boot:run
\`\`\`
Backend: http://localhost:8080  
Health: http://localhost:8080/api/health

## 3. Start worker
\`\`\`bash
cd worker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

gcloud auth application-default login
export GCP_PROJECT="agentos-514612"
export GCP_LOCATION="global"
export VERTEX_MODEL="gemini-3.8-flash"
export VERTEX_MAX_TOKENS=3000
export VERTEX_JOB_MAX_OUTPUT_TOKENS=4096
export VERTEX_RESUME_MAX_OUTPUT_TOKENS=5000
export JOBPILOT_JOB_VISUAL_INSPECTION_ENABLED=true
export JOBPILOT_JOB_SCREENSHOT_COUNT=4

python -m uvicorn app.main:app --reload --port 8000
\`\`\`
Worker: http://localhost:8000  
API docs: http://localhost:8000/docs

## 4. Start frontend
\`\`\`bash
cd frontend
npm install
npm run dev
\`\`\`
Frontend: http://localhost:3000

## Environment
Copy \`.env.example\` to your local \`.env\`. The worker loads that file on startup. Vertex calls use Application Default Credentials from \`gcloud auth application-default login\`; do not put a service-account key in the repo. Do not commit \`.env\`.

Generated DOCX and PDF documents are stored locally under \`storage/tailored/\` and are excluded from Git.

## Current API

### Spring Boot
- \`GET /api/health\` — backend and MongoDB health
- \`POST /api/resumes\` — upload a PDF resume
- \`GET /api/profile\` — load the saved career profile
- \`PUT /api/profile\` — save a reviewed career profile
- \`POST /api/jobs/analyze\` — analyze a public Greenhouse job against the verified profile
- \`GET /api/jobs\` — list the latest 50 saved job analyses
- \`GET /api/jobs/{id}\` — retrieve a saved job analysis
- \`POST /api/jobs/{jobId}/tailored-resumes\` — generate a job-specific resume
- \`GET /api/jobs/{jobId}/tailored-resumes\` — list generated versions for that job
- \`GET /api/tailored-resumes/{id}\` — retrieve a tailored resume and its source-linked changes
- \`GET /api/tailored-resumes/{id}/download?format=docx|pdf\` — download the generated document

### Python worker
- \`GET /health\` — worker health
- \`GET /ai/status\` — Vertex project, location, and model
- \`POST /ai/chat\` — Gemini chat completion on Vertex AI
- \`POST /resume/parse\` — extract structured career facts from a PDF
- \`POST /jobs/analyze\` — retrieve a public Greenhouse posting, extract requirements and match evidence
- \`POST /resumes/tailor\` — create a source-linked tailored resume draft and DOCX/PDF files

## Milestone 2: Resume intelligence
1. Open http://localhost:3000/profile.
2. Upload a text-based PDF resume (maximum 5 MB).
3. Spring Boot stores the PDF under \`storage/resumes/\` and calls the Python worker.
4. The worker extracts text with PyMuPDF and asks Gemini on Vertex AI for structured career facts.
5. Spring Boot stores resume metadata and the extracted profile in MongoDB (\`resumes\` and \`career_profiles\`).
6. Review and correct the extracted facts, then explicitly save and verify the profile.

Scanned/image-only PDFs are not supported yet; OCR is a future enhancement. AI extraction is a draft and must be checked before relying on it.

## Milestone 3: Greenhouse job intelligence
1. Verify your saved career profile at http://localhost:3000/profile.
2. Open http://localhost:3000/jobs.
3. Paste a public job URL with this format: \`https://boards.greenhouse.io/{board_token}/jobs/{job_id}\`. The alternate \`job-boards.greenhouse.io\` host is also accepted.
4. Spring Boot checks that the verified career profile exists and sends the URL plus profile facts (excluding contact identifiers) to the Python worker.
5. The worker validates the exact Greenhouse host and URL path, calls the public Greenhouse Job Board API with content=true, and opens the same posting in headless Chromium to capture up to four overlapping viewport screenshots.
6. The worker sends the API description, rendered-page headings/text and screenshots to Gemini on Vertex AI in one multimodal request. Gemini extracts role requirements, compares them with the career profile and returns additional job-relevant visual findings. Screenshots are held in memory for the request and are not saved to disk.
7. The worker returns requirement-level evidence plus visual-inspection status, screenshot count and visual findings. If Chromium is unavailable, JobPilot records that visual inspection was unavailable and continues with API text only. The application calculates a deterministic score: required skills 40%, experience/responsibilities 30%, project evidence 20%, and preferred skills 10%. Categories absent from the comparison are excluded and the remaining weights are normalized to total 100%.
8. Spring Boot saves the job, requirements, match evidence and visual-inspection summary in MongoDB's jobs collection. The same Greenhouse board token and job ID update the existing record rather than creating duplicates.
9. Review the score breakdown, matched evidence and gaps in the Jobs page. The score is a profile-evidence estimate, not a prediction of hiring success.

## Milestone 4: Job-specific resume tailoring
1. Open a previously analyzed job in \`/jobs\` and select **Tailor resume for this job**.
2. Spring Boot confirms the source career profile is still verified and sends the job, extracted requirements, match evidence and verified career facts to the Python worker.
3. The worker keeps contact fields out of the Gemini prompt. The model receives professional facts and source references such as \`experience:0\` and \`project:1\`.
4. Gemini proposes a targeted headline, summary, selected skills, relevant experience/project bullets and a change log. Each rewritten bullet must cite a source reference.
5. The worker validates references. Employer, job title, location, employment dates, education and certifications are copied from the saved career profile rather than regenerated by the model. Skills are restricted to skills/technologies already present in the profile.
6. The worker renders DOCX and PDF files. Spring Boot stores the files under \`storage/tailored/\` and metadata in MongoDB's \`tailored_resumes\` collection.
7. The tailoring page shows a preview, why changes were made, and the source text behind each generated bullet. Download either DOCX or PDF.
8. Review every claim before using the resume. Source references improve traceability but cannot prove that a paraphrase is semantically perfect. The master profile is never modified.

### Tailoring limitations
- The source profile needs descriptive work-history or project facts. A skills-only profile is not enough to responsibly generate experience bullets.
- A model may still overstate a source fact when paraphrasing; the human review step is mandatory.
- The PDF uses standard built-in fonts and a clean ATS-oriented layout. DOCX is editable.
- Generated documents are local files; multi-user access control and production document retention are not implemented yet.

### Supported URLs and job-analysis limitations
- Only public Greenhouse job postings on \`boards.greenhouse.io\` and \`job-boards.greenhouse.io\` are supported.
- URL validation uses an exact hostname allow-list; the worker does not fetch arbitrary user-supplied hosts.
- The job must still be publicly available through the Greenhouse Job Board API.
- Company name is not present in every public Greenhouse job payload; in that case the board token is used as a display fallback.
- Job analysis does not open an application form, fill fields, or submit anything.
- AI output can be incomplete. Confirm the job description and evidence before using the analysis to make decisions.

## Vertex smoke test
\`\`\`bash
curl -X POST http://localhost:8000/ai/chat \\
  -H 'Content-Type: application/json' \\
  -d '{"messages":[{"role":"user","content":"Reply with JobPilot AI is working"}]}'
\`\`\`

## Test job retrieval and analysis
\`\`\`bash
curl -X POST http://localhost:8080/api/jobs/analyze \\
  -H 'Content-Type: application/json' \\
  -d '{"url":"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"}'
\`\`\`
Replace the example URL with a currently published public Greenhouse posting.

## Worker unit tests
From the \`worker\` directory, with the worker dependencies installed:
\`\`\`bash
python -m unittest discover -s tests -v
\`\`\`

## Security and limitations
- This is a local-development MVP, not production-hardened.
- Authentication, authorization, multi-user isolation, encryption at rest and retention controls are not yet implemented.
- Resumes contain personal information. Only upload files you are authorized to process.
- Keep \`.env\`, API keys, local virtual environments, build outputs and uploaded resumes out of Git.


## Milestone 5: Greenhouse application automation

1. Run the Python worker on the same Mac/desktop where you want the visible browser window to appear. A worker hosted remotely opens its browser on that remote machine, not on your Mac.
2. Install Playwright's Chromium browser once from the worker directory: `python -m playwright install chromium`.
3. Keep `JOBPILOT_BROWSER_HEADLESS=false` in `.env`. The visible browser is intentional.
4. Open an analyzed Greenhouse job, generate and review a tailored resume, then select **Apply with JobPilot**.
5. Choose the tailored PDF and start the application. JobPilot opens the public Greenhouse posting, clicks Apply when needed, inspects the form, fills unambiguous contact fields from the verified profile and uploads the tailored PDF.
6. Complete screening questions, custom dropdowns, and any manual verification in the visible Chromium window. Return to JobPilot and select **Refresh form review**.
7. Review all fields in the browser. Check the explicit authorization box and select **Submit application** only when you are ready.
8. JobPilot reports a submission as confirmed only when a Greenhouse application-received message is detected. If the result is uncertain, it will not retry; inspect Greenhouse and your email first.

### Automation boundaries

- Only HTTPS public Greenhouse job URLs on `boards.greenhouse.io` and `job-boards.greenhouse.io` are supported.
- The worker uses a visible, local Playwright Chromium session. It is held in worker memory and expires after the configured inactivity period.
- Only clearly identified name, email, phone, LinkedIn, GitHub and portfolio/website fields are eligible for autofill, and only when values exist in the verified profile. Existing filled values are not overwritten.
- JobPilot does not guess answers about salary, notice period, work authorization, sponsorship, relocation, demographics, or screening questions. Sensitive fields remain manual.
- CAPTCHA, identity checks and bot protections must be completed manually. JobPilot does not bypass them.
- The form checklist stores field labels and completion flags, not the values typed into the application.
- This is a single-user local-development workflow. It does not yet provide authentication, per-user browser isolation, remote browser streaming, or production-grade session recovery. Do not expose the backend or worker ports to the public internet.

### New API

**Spring Boot**
- `POST /api/jobs/{jobId}/applications` with `{"tailoredResumeId":"..."}` — open the visible browser and prepare the application.
- `GET /api/jobs/{jobId}/applications` — list application sessions for a job.
- `GET /api/applications/{id}` — retrieve application state.
- `POST /api/applications/{id}/refresh` — synchronize field completion from Chromium.
- `POST /api/applications/{id}/submit` with `{"confirmSubmit":true}` — submit after explicit approval.
- `POST /api/applications/{id}/cancel` — close the browser without submitting.

**Python worker**
- `POST /applications/prepare`
- `GET /applications/{session_id}`
- `POST /applications/{session_id}/refresh`
- `POST /applications/{session_id}/submit`
- `POST /applications/{session_id}/cancel`
