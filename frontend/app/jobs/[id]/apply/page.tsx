"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type TailoredResume = {
  id: string;
  jobTitle: string;
  company: string;
  resumeStyle?: string;
  createdAt: string;
};

type ApplicationField = {
  label: string;
  type: string;
  required: boolean;
  filled: boolean;
  checked?: boolean | null;
  classification: string;
  index?: number;
  name?: string;
  id?: string;
};

type FormVerification = {
  passes_completed: number;
  passes_required: number;
  required_fields_remaining: number;
  complete: boolean;
  pass_results?: Array<{
    pass: number;
    fields_checked: number;
    safe_fills: number;
    required_fields_remaining: number;
  }>;
};

type QuestionEvidence = {
  source: string;
  path: string;
  detail: string;
};

type QuestionReviewItem = {
  field_index: number;
  question: string;
  category: string;
  evidence_status: "supported" | "partial" | "not_found" | "manual_review" | "not_reviewed";
  reason: string;
  evidence: QuestionEvidence[];
  suggested_answer?: string | null;
  profile_improvement?: string | null;
  needs_profile_update?: boolean;
  profile_fields_needed?: string[];
  answer_basis?: string | null;
  saved_profile_answer?: boolean;
  filled?: boolean;
};

type QuestionReview = {
  status: "completed" | "unavailable";
  questions_reviewed: number;
  supported_count: number;
  partial_count: number;
  not_found_count: number;
  manual_review_count: number;
  profile_update_required_count?: number;
  reviews: QuestionReviewItem[];
  profile_update_requests?: Array<{
    field_index: number;
    question: string;
    fields_needed: string[];
    recommendation: string;
    priority: "high" | "medium";
  }>;
  profile_improvements: Array<{
    field_index: number;
    question: string;
    recommendation: string;
    priority: "high" | "medium";
  }>;
  message?: string;
};

type Application = {
  id: string;
  jobId: string;
  tailoredResumeId: string;
  resumeFormat?: "pdf" | "docx";
  jobTitle: string;
  company: string;
  applicationUrl: string;
  status: string;
  fields: ApplicationField[];
  missingRequiredFields: string[];
  message: string | null;
  automationNotes?: string[];
  formVerification?: FormVerification;
  questionReview?: QuestionReview;
  createdAt: string;
  updatedAt: string;
  submittedAt?: string | null;
};

type Job = {
  job: { title: string; company: string; location?: string | null };
  jobUrl: string;
};

function responseMessage(data: any, fallback: string) {
  if (typeof data?.detail === "string") {
    try {
      const parsed = JSON.parse(data.detail);
      return parsed.detail ?? data.detail;
    } catch {
      return data.detail;
    }
  }
  return data?.message ?? fallback;
}

function questionStatusStyle(status: string) {
  if (status === "supported") return "border-emerald-300/30 bg-emerald-300/10 text-emerald-200";
  if (status === "partial") return "border-amber-300/30 bg-amber-300/10 text-amber-200";
  if (status === "not_found") return "border-rose-300/30 bg-rose-300/10 text-rose-200";
  if (status === "manual_review") return "border-slate-300/20 bg-white/[0.05] text-slate-300";
  return "border-white/15 bg-white/[0.04] text-slate-400";
}

function statusStyle(status: string) {
  if (status === "SUBMITTED") return "text-emerald-300 border-emerald-300/30 bg-emerald-300/10";
  if (status === "READY_FOR_REVIEW") return "text-cyan-200 border-cyan-300/30 bg-cyan-300/10";
  if (status === "SUBMISSION_UNKNOWN" || status === "FAILED" || status === "EXPIRED") {
    return "text-amber-200 border-amber-300/30 bg-amber-300/10";
  }
  return "text-slate-200 border-white/15 bg-white/[0.04]";
}

export default function ApplyPage() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;

  const [job, setJob] = useState<Job | null>(null);
  const [resumes, setResumes] = useState<TailoredResume[]>([]);
  const [selectedResumeId, setSelectedResumeId] = useState("");
  const [selectedFormat, setSelectedFormat] = useState<"pdf" | "docx">("pdf");
  const [application, setApplication] = useState<Application | null>(null);
  const [confirmReviewed, setConfirmReviewed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [answerDrafts, setAnswerDrafts] = useState<Record<number, string>>({});
  const [questionLabelDrafts, setQuestionLabelDrafts] = useState<Record<number, string>>({});
  const [savingAnswerFor, setSavingAnswerFor] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [jobResponse, resumeResponse, applicationResponse] = await Promise.all([
          fetch(API + "/api/jobs/" + encodeURIComponent(jobId), { cache: "no-store" }),
          fetch(API + "/api/jobs/" + encodeURIComponent(jobId) + "/tailored-resumes", { cache: "no-store" }),
          fetch(API + "/api/jobs/" + encodeURIComponent(jobId) + "/applications", { cache: "no-store" }),
        ]);
        if (!jobResponse.ok) throw new Error("Could not load this analyzed job.");
        const jobData: Job = await jobResponse.json();
        const resumeData: TailoredResume[] = resumeResponse.ok ? await resumeResponse.json() : [];
        const applicationData: Application[] = applicationResponse.ok ? await applicationResponse.json() : [];
        if (!active) return;
        setJob(jobData);
        setResumes(resumeData);
        if (resumeData.length) setSelectedResumeId(resumeData[0].id);
        if (applicationData.length) setApplication(applicationData[0]);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Could not load the application workspace.");
      } finally {
        if (active) setLoading(false);
      }
    }
    if (jobId) void load();
    return () => { active = false; };
  }, [jobId]);

  async function startApplication() {
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(API + "/api/jobs/" + encodeURIComponent(jobId) + "/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tailoredResumeId: selectedResumeId, format: selectedFormat }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, "Could not start the application."));
      setApplication(data as Application);
      setConfirmReviewed(false);
      setNotice("The visible Greenhouse browser is open. Complete any remaining fields there.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the application.");
    } finally {
      setWorking(false);
    }
  }

  async function refreshReview() {
    if (!application) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(API + "/api/applications/" + encodeURIComponent(application.id) + "/refresh", {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, "Could not refresh the form review."));
      setApplication(data as Application);
      setConfirmReviewed(false);
      setNotice("Form state refreshed from the visible browser.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refresh the form review.");
    } finally {
      setWorking(false);
    }
  }

  async function saveAnswerForFuture(review: QuestionReviewItem) {
    if (!application) return;
    const question = review.category === "unlabelled_field"
      ? (questionLabelDrafts[review.field_index] ?? "").trim()
      : review.question.trim();
    const answer = (answerDrafts[review.field_index] ?? "").trim();

    if (!question) {
      setError("Describe what the unlabelled field is asking before saving an answer.");
      return;
    }
    if (!answer) {
      setError("Enter an answer before saving it to your profile.");
      return;
    }

    setSavingAnswerFor(review.field_index);
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const saveResponse = await fetch(API + "/api/profile/application-answers", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          answer,
          classification: review.category,
        }),
      });
      const savedData = await saveResponse.json();
      if (!saveResponse.ok) throw new Error(responseMessage(savedData, "Could not save this answer to your career profile."));

      // Refresh sends the latest verified profile back to the open browser session.
      // The field index is used only for this current form; future forms use the saved question match.
      const refreshResponse = await fetch(API + "/api/applications/" + encodeURIComponent(application.id) + "/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manualAnswer: {
            fieldIndex: review.field_index,
            question,
            answer,
          },
        }),
      });
      const refreshedData = await refreshResponse.json();
      if (!refreshResponse.ok) {
        setNotice("Your answer was saved to your career profile. Refresh the form manually to apply it to this open application.");
        throw new Error(responseMessage(refreshedData, "The answer was saved, but the current form could not be refreshed."));
      }

      setApplication(refreshedData as Application);
      setConfirmReviewed(false);
      setAnswerDrafts(current => ({ ...current, [review.field_index]: "" }));
      setQuestionLabelDrafts(current => ({ ...current, [review.field_index]: "" }));
      setNotice("Answer saved in your career profile and applied to the current form where the control supports it. JobPilot can reuse it for matching questions in future applications.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this application answer.");
    } finally {
      setSavingAnswerFor(null);
      setWorking(false);
    }
  }

  async function submitApplication() {
    if (!application || !confirmReviewed || application.status !== "READY_FOR_REVIEW") return;
    const confirmed = window.confirm(
      "Submit this application to the employer now? This is the final action and may not be reversible."
    );
    if (!confirmed) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(API + "/api/applications/" + encodeURIComponent(application.id) + "/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmSubmit: true }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, "The submission request failed."));
      setApplication(data as Application);
      setConfirmReviewed(false);
      setNotice(data.status === "SUBMITTED"
        ? "Greenhouse showed a successful application-received confirmation."
        : "The submit control was activated. Verify the result in the open browser before doing anything else.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the application.");
    } finally {
      setWorking(false);
    }
  }

  async function cancelApplication() {
    if (!application) return;
    setWorking(true);
    setError("");
    try {
      const response = await fetch(API + "/api/applications/" + encodeURIComponent(application.id) + "/cancel", {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, "Could not close the browser session."));
      setApplication(data as Application);
      setConfirmReviewed(false);
      setNotice("The application browser session was closed without submitting.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not close the browser session.");
    } finally {
      setWorking(false);
    }
  }

  if (loading) {
    return <main className="min-h-screen px-6 py-10"><div className="mx-auto max-w-5xl text-slate-400">Loading application workspace...</div></main>;
  }

  const terminal = ["SUBMITTING", "SUBMITTED", "SUBMISSION_UNKNOWN", "CANCELLED", "FAILED", "EXPIRED"].includes(application?.status ?? "");

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <div className="mx-auto max-w-5xl">
        <a href="/jobs" className="text-sm text-cyan-300">← Back to jobs</a>
        <header className="mt-6">
          <div className="text-xs font-semibold tracking-[0.22em] text-cyan-300">GREENHOUSE APPLICATION</div>
          <h1 className="mt-3 text-3xl font-semibold md:text-4xl">Review and apply</h1>
          {job && <p className="mt-3 text-slate-400">{job.job.title} · {job.job.company}{job.job.location ? " · " + job.job.location : ""}</p>}
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
            JobPilot opens a visible Chromium window, fills only clearly identified contact fields from your verified profile,
            and uploads the selected tailored PDF or Word document. Complete screening questions yourself in the browser.
            Nothing is submitted until you review the form and explicitly confirm here.
          </p>
        </header>

        {error && <div role="alert" className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-200">{error}</div>}
        {notice && <div role="status" className="mt-5 rounded-xl border border-emerald-400/20 bg-emerald-400/10 p-4 text-sm text-emerald-200">{notice}</div>}

        {!application && (
          <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
            <h2 className="text-lg font-semibold">Choose the tailored resume to upload</h2>
            {resumes.length ? (
              <>
                <div className="mt-4 space-y-3">
                  {resumes.map((resume, index) => (
                    <label key={resume.id} className={"flex cursor-pointer items-center gap-3 rounded-xl border p-4 " + (
                      selectedResumeId === resume.id ? "border-cyan-300/40 bg-cyan-300/5" : "border-white/10"
                    )}>
                      <input
                        type="radio"
                        name="tailoredResume"
                        value={resume.id}
                        checked={selectedResumeId === resume.id}
                        onChange={() => setSelectedResumeId(resume.id)}
                      />
                      <span className="min-w-0">
                        <span className="block font-medium">{resume.jobTitle} · {resume.company}</span>
                        <span className="mt-1 block text-xs text-slate-400">
                          Version {resumes.length - index} · {resume.resumeStyle ?? "ATS Classic"} · {new Date(resume.createdAt).toLocaleString()}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
                <div className="mt-5">
                  <h3 className="text-sm font-semibold">Resume file to attach</h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <label className={"flex cursor-pointer items-start gap-3 rounded-xl border p-4 " + (
                      selectedFormat === "pdf" ? "border-cyan-300/50 bg-cyan-300/10" : "border-white/10"
                    )}>
                      <input
                        type="radio"
                        name="resumeFormat"
                        value="pdf"
                        checked={selectedFormat === "pdf"}
                        onChange={() => setSelectedFormat("pdf")}
                      />
                      <span>
                        <span className="block font-medium">PDF</span>
                        <span className="mt-1 block text-xs text-slate-400">Recommended for most ATS portals.</span>
                      </span>
                    </label>
                    <label className={"flex cursor-pointer items-start gap-3 rounded-xl border p-4 " + (
                      selectedFormat === "docx" ? "border-cyan-300/50 bg-cyan-300/10" : "border-white/10"
                    )}>
                      <input
                        type="radio"
                        name="resumeFormat"
                        value="docx"
                        checked={selectedFormat === "docx"}
                        onChange={() => setSelectedFormat("docx")}
                      />
                      <span>
                        <span className="block font-medium">Word (.docx)</span>
                        <span className="mt-1 block text-xs text-slate-400">Choose when the employer accepts Word documents.</span>
                      </span>
                    </label>
                  </div>
                </div>
                <button
                  onClick={startApplication}
                  disabled={working || !selectedResumeId}
                  className="mt-5 rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-slate-950 disabled:opacity-40"
                >
                  {working ? "Opening Greenhouse..." : "Open application in browser"}
                </button>
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                No tailored resume exists for this job yet. <a className="text-cyan-300 underline" href={"/jobs/" + encodeURIComponent(jobId) + "/tailor"}>Generate and review one first</a>.
              </p>
            )}
          </section>
        )}

        {application && (
          <>
            <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-xs tracking-wider text-slate-400">APPLICATION STATUS</div>
                  <div className={"mt-2 inline-flex rounded-full border px-3 py-1 text-sm font-semibold " + statusStyle(application.status)}>
                    {application.status.replaceAll("_", " ")}
                  </div>
                </div>
                {application.applicationUrl && (
                  <a className="text-sm text-cyan-300 underline" href={application.applicationUrl} target="_blank" rel="noreferrer">
                    Open application page ↗
                  </a>
                )}
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-300">{application.message}</p>
              {application.formVerification && (
                <div className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-semibold text-cyan-100">Agentic form verification</h3>
                    <span className="text-xs text-slate-300">
                      {application.formVerification.passes_completed}/{application.formVerification.passes_required} passes
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-300">
                    {application.formVerification.complete
                      ? "All required controls were detected as complete after verification."
                      : application.formVerification.required_fields_remaining + " required field(s) remain after three checks. Complete these in Chromium and refresh again."}
                  </p>
                  {!!application.formVerification.pass_results?.length && (
                    <div className="mt-3 grid gap-2 sm:grid-cols-3">
                      {application.formVerification.pass_results.map(result => (
                        <div key={result.pass} className="rounded-lg border border-white/10 bg-slate-950/40 p-3 text-xs text-slate-300">
                          <div className="font-semibold">Pass {result.pass}</div>
                          <div className="mt-1">{result.fields_checked} controls checked</div>
                          <div>{result.safe_fills} safe fill actions</div>
                          <div>{result.required_fields_remaining} required remaining</div>
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="mt-3 text-xs leading-5 text-slate-400">
                    The agent will not guess prior-employment, eligibility, screening, privacy-consent or unidentified answers.
                  </p>
                </div>
              )}
              <p className="mt-1 text-xs text-slate-400">
                Attached resume format: {(application.resumeFormat ?? "pdf").toUpperCase()}
              </p>
              {!!application.automationNotes?.length && (
                <div className="mt-3 rounded-xl border border-amber-300/20 bg-amber-300/5 p-4">
                  <h3 className="text-sm font-semibold text-amber-100">Automation notes</h3>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-300">
                    {application.automationNotes.map((note, index) => <li key={index}>{note}</li>)}
                  </ul>
                </div>
              )}
              <div className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4 text-sm leading-6 text-slate-300">
                <strong className="text-cyan-100">Look for the Chromium window.</strong> It is displayed on the computer running
                the Python worker. Complete unanswered screening questions, dropdowns, and any manual verification there.
                Return here and select <strong>Refresh form review</strong> afterward.
              </div>

              <div className="mt-6 flex flex-wrap gap-3">
                {!terminal && (
                  <button onClick={refreshReview} disabled={working} className="rounded-xl border border-white/20 px-4 py-2.5 text-sm font-semibold disabled:opacity-40">
                    {working ? "Checking..." : "Refresh form review"}
                  </button>
                )}
                {!terminal && (
                  <button onClick={cancelApplication} disabled={working} className="rounded-xl border border-rose-300/30 px-4 py-2.5 text-sm font-semibold text-rose-200 disabled:opacity-40">
                    Close browser without submitting
                  </button>
                )}
                {["CANCELLED", "FAILED", "EXPIRED"].includes(application.status) && (
                  <button onClick={() => { setApplication(null); setNotice(""); setError(""); }} className="rounded-xl border border-white/20 px-4 py-2.5 text-sm font-semibold">
                    Start a new session
                  </button>
                )}
              </div>
            </section>

            <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
              <h2 className="text-lg font-semibold">Form field checklist</h2>
              <p className="mt-1 text-sm text-slate-400">JobPilot stores labels and completion flags only; it does not copy your entered answers into this checklist.</p>
              {application.fields.some(field => field.type === "checkbox") && (
                <div className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/5 p-4 text-sm leading-6 text-amber-100">
                  Checkbox choices are read from the live Greenhouse form. JobPilot will not auto-check consent,
                  eligibility, demographic or screening answers. Choose only options that are true for you in Chromium,
                  then refresh this review. Any required unchecked checkbox blocks submission.
                </div>
              )}
              <div className="mt-4 space-y-2">
                {application.fields.map((field, index) => (
                  <div key={(field.id || field.name || field.label) + index} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 px-4 py-3">
                    <span className="min-w-0 text-sm text-slate-200">
                      {field.label}{field.required ? <span className="text-rose-300"> *</span> : ""}
                      {field.type === "checkbox" && (
                        <span className="mt-1 block text-xs text-slate-500">
                          {field.classification === "sensitive_or_eligibility" ? "Sensitive / eligibility choice" : "Checkbox"}
                        </span>
                      )}
                    </span>
                    {field.type === "checkbox" ? (
                      <span className={"inline-flex items-center gap-2 text-xs font-medium " + (
                        field.filled ? "text-emerald-300" : field.required ? "text-amber-200" : "text-slate-500"
                      )}>
                        <input type="checkbox" checked={Boolean(field.filled)} readOnly disabled />
                        {field.filled ? "Checked in Chromium" : field.required ? "Required — unchecked" : "Not checked"}
                      </span>
                    ) : (
                      <span className={"text-xs font-medium " + (field.filled ? "text-emerald-300" : field.required ? "text-amber-200" : "text-slate-500")}>
                        {field.filled ? "Detected as complete" : field.required ? "Needs attention" : "Optional / blank"}
                      </span>
                    )}
                  </div>
                ))}
                {!application.fields.length && <p className="text-sm text-slate-500">No form fields were returned. Check the open browser or start a new session.</p>}
              </div>

              {application.missingRequiredFields.length > 0 && (
                <div className="mt-5 rounded-xl border border-amber-300/20 bg-amber-300/5 p-4">
                  <h3 className="font-semibold text-amber-100">Required fields still missing</h3>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
                    {application.missingRequiredFields.map((field, index) => <li key={field + index}>{field}</li>)}
                  </ul>
                </div>
              )}
            </section>

            {application.questionReview && Array.isArray(application.questionReview.reviews) && (
              <section className="mt-5 rounded-2xl border border-violet-300/20 bg-violet-300/[0.04] p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">Question-to-profile match</h2>
                    <p className="mt-1 text-sm leading-6 text-slate-400">
                      JobPilot compares application questions with your verified profile and tailored resume, resolves structured facts where possible, and identifies missing details. Suggested answers are drafts only; they are never entered automatically.
                    </p>
                  </div>
                  <span className="rounded-full border border-violet-300/30 bg-violet-300/10 px-3 py-1 text-xs font-medium text-violet-200">
                    {application.questionReview.questions_reviewed} questions reviewed
                  </span>
                </div>
                {application.questionReview.status === "unavailable" && (
                  <p className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/5 p-3 text-sm text-amber-100">
                    AI question review is temporarily unavailable. Do not infer answers; review your profile and resume manually.
                  </p>
                )}
                <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                  {[
                    ["Supported", application.questionReview.supported_count],
                    ["Partial", application.questionReview.partial_count],
                    ["Not found", application.questionReview.not_found_count],
                    ["Manual", application.questionReview.manual_review_count],
                    ["Profile updates", application.questionReview.profile_update_required_count ?? 0],
                  ].map(([label, count]) => (
                    <div key={String(label)} className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
                      <div className="text-xs text-slate-400">{label}</div>
                      <div className="mt-1 text-xl font-semibold tabular-nums">{count}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 space-y-3">
                  {application.questionReview.reviews.map(review => (
                    <article key={review.field_index} className="rounded-xl border border-white/10 bg-slate-950/30 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <h3 className="min-w-0 flex-1 text-sm font-semibold text-slate-100">{review.question}</h3>
                        <span className={"rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide " + questionStatusStyle(review.needs_profile_update ? "partial" : review.evidence_status)}>
                          {review.needs_profile_update ? "profile update required" : review.evidence_status.replaceAll("_", " ")}
                        </span>
                      </div>
                      {review.reason && <p className="mt-2 text-sm leading-6 text-slate-300">{review.reason}</p>}
                      {review.saved_profile_answer && (
                        <p className="mt-2 text-xs font-medium text-emerald-200">
                          Reused an answer you previously saved in your career profile.
                        </p>
                      )}
                      {!!review.evidence?.length && (
                        <div className="mt-3 space-y-2">
                          {review.evidence.map((source, index) => (
                            <div key={source.source + source.path + index} className="rounded-lg bg-white/[0.035] p-3">
                              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                                {source.source === "verified_profile" ? "Verified career profile" : "Tailored resume"} · {source.path}
                              </div>
                              <p className="mt-1 text-xs leading-5 text-slate-300">{source.detail}</p>
                            </div>
                          ))}
                        </div>
                      )}
                      {review.answer_basis && (
                        <p className="mt-2 text-xs text-slate-500">Answer basis: {review.answer_basis}</p>
                      )}
                      {review.suggested_answer && (
                        <div className="mt-3 rounded-lg border border-emerald-300/15 bg-emerald-300/[0.05] p-3">
                          <div className="text-xs font-semibold text-emerald-200">Evidence-backed answer draft — review before using</div>
                          <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-200">{review.suggested_answer}</p>
                        </div>
                      )}
                      {!!review.profile_fields_needed?.length && (
                        <div className="mt-3 rounded-lg border border-amber-300/15 bg-amber-300/[0.05] p-3">
                          <div className="text-xs font-semibold text-amber-200">Missing profile fields</div>
                          <p className="mt-1 text-sm text-slate-300">
                            {review.profile_fields_needed.map(field => field.replaceAll("_", " ")).join(", ")}
                          </p>
                        </div>
                      )}
                      {review.profile_improvement && (
                        <div className="mt-3 rounded-lg border border-amber-300/15 bg-amber-300/[0.05] p-3">
                          <div className="text-xs font-semibold text-amber-200">Possible profile improvement</div>
                          <p className="mt-1 text-sm leading-6 text-slate-300">{review.profile_improvement}</p>
                        </div>
                      )}
                      {!review.filled
                        && !["sensitive_or_eligibility", "checkbox_review", "sensitive_or_candidate_decision"].includes(review.category)
                        && (review.evidence_status !== "supported" || !review.suggested_answer)
                        && (
                          <div className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.045] p-4">
                            <div className="text-sm font-semibold text-cyan-100">
                              {review.category === "unlabelled_field"
                                ? "Tell JobPilot what this field is asking"
                                : "Add an answer to your reusable profile"}
                            </div>
                            <p className="mt-1 text-xs leading-5 text-slate-400">
                              Your answer will be saved as extra career-profile information and can be reused when a future job application asks the same or a matching question.
                            </p>
                            {review.category === "unlabelled_field" && (
                              <label className="mt-3 block text-xs text-slate-300">
                                What is the question or field asking?
                                <input
                                  value={questionLabelDrafts[review.field_index] ?? ""}
                                  onChange={event => setQuestionLabelDrafts(current => ({ ...current, [review.field_index]: event.target.value }))}
                                  placeholder="Describe the field in your own words"
                                  className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-300"
                                />
                              </label>
                            )}
                            <label className="mt-3 block text-xs text-slate-300">
                              Your answer
                              <textarea
                                rows={3}
                                value={answerDrafts[review.field_index] ?? ""}
                                onChange={event => setAnswerDrafts(current => ({ ...current, [review.field_index]: event.target.value }))}
                                placeholder="Enter an accurate answer you would use for this question"
                                className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-300"
                              />
                            </label>
                            <button
                              type="button"
                              onClick={() => void saveAnswerForFuture(review)}
                              disabled={working || savingAnswerFor !== null}
                              className="mt-3 rounded-lg bg-cyan-300 px-4 py-2 text-xs font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                              {savingAnswerFor === review.field_index ? "Saving and refreshing..." : "Save to profile for future applications"}
                            </button>
                          </div>
                        )}
                    </article>
                  ))}
                </div>
                {!!application.questionReview.profile_update_requests?.length && (
                  <div className="mt-5 rounded-xl border border-amber-300/25 bg-amber-300/[0.07] p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-semibold text-amber-100">Your profile needs more information</h3>
                      <a href="/profile" className="text-xs font-semibold text-cyan-300 underline">Update career profile ↗</a>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-slate-400">
                      Add only accurate information. JobPilot will use the saved values the next time it reviews this application.
                    </p>
                    <ul className="mt-3 space-y-3">
                      {application.questionReview.profile_update_requests.map((item, index) => (
                        <li key={item.field_index + "-required-" + index} className="text-sm leading-6 text-slate-200">
                          <span className="font-medium">{item.question}</span>
                          <p className="mt-1 text-slate-300">{item.recommendation}</p>
                          {!!item.fields_needed?.length && (
                            <p className="mt-1 text-xs text-amber-100/80">
                              Add: {item.fields_needed.map(field => field.replaceAll("_", " ")).join(", ")}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {!!application.questionReview.profile_improvements?.length && (
                  <div className="mt-5 rounded-xl border border-amber-300/20 bg-amber-300/5 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-semibold text-amber-100">Improve your career profile</h3>
                      <a href="/profile" className="text-xs font-semibold text-cyan-300 underline">Open career profile ↗</a>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-slate-400">Only add details that are accurate and that you can support in an interview.</p>
                    <ul className="mt-3 space-y-3">
                      {application.questionReview.profile_improvements.map((item, index) => (
                        <li key={item.field_index + "-" + index} className="text-sm leading-6 text-slate-200">
                          <span className="mr-2 rounded border border-amber-300/20 px-1.5 py-0.5 text-[10px] uppercase text-amber-200">{item.priority}</span>
                          <span className="font-medium">{item.question}</span>
                          <p className="mt-1 text-slate-300">{item.recommendation}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="mt-4 text-xs leading-5 text-slate-500">
                  JobPilot never checks consent boxes or answers demographic, eligibility, prior-employment or other sensitive declarations. These remain your decision.
                </p>
              </section>
            )}
            {application.status === "READY_FOR_REVIEW" && (
              <section className="mt-5 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.04] p-6">
                <h2 className="text-lg font-semibold">Final human approval</h2>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  Open Chromium and inspect every field, the selected resume, and every answer. A green checklist does not
                  verify that a screening answer is truthful or appropriate; you remain responsible for the final application.
                </p>
                <label className="mt-5 flex items-start gap-3 text-sm leading-6 text-slate-200">
                  <input type="checkbox" checked={confirmReviewed} onChange={event => setConfirmReviewed(event.target.checked)} className="mt-1" />
                  I reviewed the complete application in Chromium and authorize JobPilot to submit it now.
                </label>
                <button
                  onClick={submitApplication}
                  disabled={working || !confirmReviewed}
                  className="mt-5 rounded-xl bg-emerald-300 px-5 py-3 font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {working ? "Submitting..." : "Submit application"}
                </button>
              </section>
            )}

            {application.status === "SUBMITTING" && (
              <section className="mt-5 rounded-xl border border-amber-300/20 bg-amber-300/5 p-5 text-sm leading-6 text-amber-100">
                Submission is in progress or awaiting confirmation. Do not start another submission. Check the open Chromium
                window, then reload this page to retrieve the saved status.
              </section>
            )}
            {application.status === "SUBMISSION_UNKNOWN" && (
              <section className="mt-5 rounded-xl border border-amber-300/20 bg-amber-300/5 p-5 text-sm leading-6 text-amber-100">
                Do not click submit again yet. Check the Greenhouse page and your email for confirmation first. JobPilot will not automatically retry an uncertain submission.
              </section>
            )}
            {application.status === "SUBMITTED" && (
              <section className="mt-5 rounded-xl border border-emerald-300/20 bg-emerald-300/5 p-5 text-sm leading-6 text-emerald-100">
                Application submitted. Save any confirmation number displayed by Greenhouse and check your email for the employer's receipt.
              </section>
            )}
          </>
        )}
      </div>
    </main>
  );
}
