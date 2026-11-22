"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type TailoredResume = {
  id: string;
  jobTitle: string;
  company: string;
  createdAt: string;
};

type ApplicationField = {
  label: string;
  type: string;
  required: boolean;
  filled: boolean;
  classification: string;
};

type Application = {
  id: string;
  jobId: string;
  tailoredResumeId: string;
  jobTitle: string;
  company: string;
  applicationUrl: string;
  status: string;
  fields: ApplicationField[];
  missingRequiredFields: string[];
  message: string | null;
  automationNotes?: string[];
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
  const [application, setApplication] = useState<Application | null>(null);
  const [confirmReviewed, setConfirmReviewed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

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
        body: JSON.stringify({ tailoredResumeId: selectedResumeId }),
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
            and uploads the selected tailored PDF. Complete screening questions yourself in the browser.
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
                          Version {resumes.length - index} · {new Date(resume.createdAt).toLocaleString()}
                        </span>
                      </span>
                    </label>
                  ))}
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
              <div className="mt-4 space-y-2">
                {application.fields.map((field, index) => (
                  <div key={field.label + index} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 px-4 py-3">
                    <span className="text-sm text-slate-200">{field.label}{field.required ? <span className="text-rose-300"> *</span> : ""}</span>
                    <span className={"text-xs font-medium " + (field.filled ? "text-emerald-300" : field.required ? "text-amber-200" : "text-slate-500")}>
                      {field.filled ? "Detected as complete" : field.required ? "Needs attention" : "Optional / blank"}
                    </span>
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
