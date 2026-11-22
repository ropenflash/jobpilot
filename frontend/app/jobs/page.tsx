"use client";

import { useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type Evidence = {
  category: string;
  requirement: string;
  profile_evidence: string;
  assessment: "matched" | "partial" | "not_evidenced";
};

type JobAnalysis = {
  id: string;
  source: string;
  jobUrl: string;
  job: {
    job_id: number;
    board_token: string;
    title: string;
    company: string;
    location?: string | null;
    description: string;
    updated_at?: string | null;
  };
  requirements: {
    summary: string;
    responsibilities: string[];
    required_skills: string[];
    preferred_skills: string[];
    qualifications: string[];
    minimum_experience_years?: number | null;
    maximum_experience_years?: number | null;
    employment_type?: string | null;
    salary_range?: string | null;
  };
  match: {
    score: number;
    recommendation: "strong_match" | "possible_match" | "weak_match";
    strengths: string[];
    gaps: string[];
    evidence: Evidence[];
    score_breakdown: {
      category: string;
      weight_percentage: number;
      category_score: number;
      evidence_count: number;
    }[];
    rationale: string;
  };
  createdAt: string;
  updatedAt: string;
};

function messageFromResponse(data: any, fallback: string) {
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

function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase());
}

export default function JobsPage() {
  const [url, setUrl] = useState("");
  const [jobs, setJobs] = useState<JobAnalysis[]>([]);
  const [selected, setSelected] = useState<JobAnalysis | null>(null);
  const [verified, setVerified] = useState(false);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadWorkspace() {
    try {
      const [profileResponse, jobsResponse] = await Promise.all([
        fetch(`${API}/api/profile`, { cache: "no-store" }),
        fetch(`${API}/api/jobs`, { cache: "no-store" }),
      ]);

      if (profileResponse.ok) {
        const profile = await profileResponse.json();
        setVerified(Boolean(profile.configured && profile.verified));
      }

      if (jobsResponse.ok) {
        const savedJobs: JobAnalysis[] = await jobsResponse.json();
        setJobs(savedJobs);
        if (savedJobs.length) setSelected(savedJobs[0]);
      }
    } catch {
      setError("Could not reach JobPilot. Check that Spring Boot and MongoDB are running.");
    } finally {
      setProfileLoaded(true);
    }
  }

  useEffect(() => { void loadWorkspace(); }, []);

  async function analyze(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setSelected(null);

    if (!verified) {
      setError("Verify your career profile before analyzing a job.");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API}/api/jobs/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(messageFromResponse(data, "Job analysis failed."));
      }

      const analysis = data as JobAnalysis;
      setSelected(analysis);
      setJobs(current => [analysis, ...current.filter(item => item.id !== analysis.id)]);
      setMessage("Job retrieved and analyzed. Review the evidence before deciding whether to proceed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job analysis failed.");
    } finally {
      setLoading(false);
    }
  }

  const active = selected;
  const recommendationColor = active?.match.recommendation === "strong_match"
    ? "text-emerald-300"
    : active?.match.recommendation === "possible_match"
      ? "text-amber-300"
      : "text-rose-300";
  const groupedEvidence = useMemo(() => {
    if (!active) return [];
    const order = [
      "required_skill",
      "experience_responsibilities",
      "project_evidence",
      "preferred_skill",
    ];
    return order
      .map(category => ({
        category,
        items: active.match.evidence.filter(item => item.category === category),
      }))
      .filter(group => group.items.length);
  }, [active]);

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <div className="mx-auto max-w-6xl">
        <a href="/" className="text-sm text-cyan-300">← Dashboard</a>

        <header className="mt-6">
          <div className="text-xs font-semibold tracking-[0.22em] text-cyan-300">JOB INTELLIGENCE</div>
          <h1 className="mt-3 text-3xl font-semibold md:text-4xl">Analyze a job</h1>
          <p className="mt-3 max-w-2xl leading-7 text-slate-400">
            Paste a public Greenhouse job URL. JobPilot retrieves the posting, extracts requirements
            and compares them with your verified career profile. Your master profile is not changed.
          </p>
        </header>

        <form onSubmit={analyze} className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <label className="block text-sm text-slate-300" htmlFor="job-url">Greenhouse job URL</label>
          <div className="mt-2 flex flex-col gap-3 sm:flex-row">
            <input
              id="job-url"
              type="url"
              required
              value={url}
              onChange={event => setUrl(event.target.value)}
              placeholder="https://boards.greenhouse.io/company/jobs/123456"
              className="min-w-0 flex-1 rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-slate-100 outline-none focus:border-cyan-300"
            />
            <button
              disabled={loading || !url.trim() || !verified}
              className="rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-slate-950 disabled:opacity-40"
            >
              {loading ? "Retrieving and analyzing..." : "Analyze job"}
            </button>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Public Greenhouse postings only for this milestone. No application form is opened or submitted.
          </p>
          {profileLoaded && !verified && (
            <p className="mt-3 text-sm text-amber-200">
              Your career profile is not verified yet. <a className="underline" href="/profile">Review your profile</a>.
            </p>
          )}
        </form>

        {error && <div role="alert" className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-200">{error}</div>}
        {message && <div role="status" className="mt-5 rounded-xl border border-emerald-400/20 bg-emerald-400/10 p-4 text-sm text-emerald-200">{message}</div>}

        {active && (
          <>
            <section className="mt-8 grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
              <article className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
                <div className="text-xs tracking-wider text-slate-400">JOB POSTING</div>
                <h2 className="mt-2 text-2xl font-semibold">{active.job.title}</h2>
                <p className="mt-2 text-slate-300">{active.job.company}</p>
                <p className="mt-1 text-sm text-slate-400">{active.job.location || "Location not stated"}</p>
                <a href={active.jobUrl} target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm text-cyan-300 underline">
                  Open original job posting ↗
                </a>
                <a href={"/jobs/" + encodeURIComponent(active.id) + "/tailor"} className="mt-4 ml-4 inline-block text-sm font-semibold text-emerald-300 underline">
                  Tailor resume for this job →
                </a>

                <div className="mt-6 border-t border-white/10 pt-5">
                  <div className="text-xs tracking-wider text-slate-400">PROFILE MATCH ESTIMATE</div>
                  <div className="mt-2 flex items-end gap-2">
                    <span className="text-5xl font-semibold tabular-nums">{active.match.score}</span>
                    <span className="pb-1 text-slate-400">/ 100</span>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                    <div className="h-full rounded-full bg-cyan-300" style={{ width: `${active.match.score}%` }} />
                  </div>
                  <div className={`mt-3 text-sm font-semibold ${recommendationColor}`}>
                    {label(active.match.recommendation)}
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-300">{active.match.rationale}</p>
                  <p className="mt-3 text-xs leading-5 text-slate-500">
                    This is an evidence-based comparison against the information in your profile, not a prediction of interview or hiring success.
                  </p>
                </div>
              </article>

              <article className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
                <h3 className="text-lg font-semibold">Role summary</h3>
                <p className="mt-2 text-sm leading-6 text-slate-300">{active.requirements.summary}</p>

                <h3 className="mt-6 font-semibold">Required skills</h3>
                <div className="mt-2 flex flex-wrap gap-2">
                  {active.requirements.required_skills.map(skill => (
                    <span key={skill} className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">{skill}</span>
                  ))}
                  {!active.requirements.required_skills.length && <span className="text-sm text-slate-500">Not specified</span>}
                </div>

                <h3 className="mt-5 font-semibold">Preferred skills</h3>
                <div className="mt-2 flex flex-wrap gap-2">
                  {active.requirements.preferred_skills.map(skill => (
                    <span key={skill} className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-300">{skill}</span>
                  ))}
                  {!active.requirements.preferred_skills.length && <span className="text-sm text-slate-500">Not specified</span>}
                </div>

                <h3 className="mt-6 font-semibold">Responsibilities</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-300">
                  {active.requirements.responsibilities.map((item, index) => <li key={index}>{item}</li>)}
                  {!active.requirements.responsibilities.length && <li className="list-none text-slate-500">Not specified</li>}
                </ul>

                <h3 className="mt-6 font-semibold">Qualifications</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-300">
                  {active.requirements.qualifications.map((item, index) => <li key={index}>{item}</li>)}
                  {!active.requirements.qualifications.length && <li className="list-none text-slate-500">Not specified</li>}
                </ul>

                <div className="mt-6 grid gap-3 border-t border-white/10 pt-5 sm:grid-cols-2">
                  <div>
                    <div className="text-xs text-slate-500">Experience range</div>
                    <p className="mt-1 text-sm text-slate-200">
                      {active.requirements.minimum_experience_years ?? "Not specified"}
                      {active.requirements.maximum_experience_years != null
                        ? `–${active.requirements.maximum_experience_years} years`
                        : active.requirements.minimum_experience_years != null ? "+ years" : ""}
                    </p>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Salary</div>
                    <p className="mt-1 text-sm text-slate-200">{active.requirements.salary_range || "Not stated"}</p>
                  </div>
                </div>
              </article>
            </section>

            <section className="mt-5 grid gap-5 md:grid-cols-2">
              <article className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
                <h3 className="font-semibold text-emerald-200">Where your profile aligns</h3>
                <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                  {active.match.strengths.map((item, index) => <li key={index}>✓ {item}</li>)}
                  {!active.match.strengths.length && <li className="text-slate-500">No strengths identified from the supplied profile.</li>}
                </ul>
              </article>
              <article className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
                <h3 className="font-semibold text-amber-200">Gaps or evidence to clarify</h3>
                <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                  {active.match.gaps.map((item, index) => <li key={index}>• {item}</li>)}
                  {!active.match.gaps.length && <li className="text-slate-500">No major gaps identified.</li>}
                </ul>
              </article>
            </section>

            <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
              <h3 className="text-lg font-semibold">Evidence behind the score</h3>
              <p className="mt-1 text-sm text-slate-400">
                Matched = direct evidence · Partial = related evidence · Not evidenced = not found in the saved profile.
              </p>
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                {active.match.score_breakdown.map(item => (
                  <div key={item.category} className="rounded-xl border border-white/10 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium">{label(item.category)}</span>
                      <span className="text-sm font-semibold">{item.category_score}%</span>
                    </div>
                    <div className="mt-2 h-1.5 rounded-full bg-white/10">
                      <div className="h-1.5 rounded-full bg-cyan-300" style={{ width: `${item.category_score}%` }} />
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      {item.weight_percentage}% of score · {item.evidence_count} evidence items
                    </p>
                  </div>
                ))}
              </div>
              <div className="mt-5 space-y-5">
                {groupedEvidence.map(group => (
                  <div key={group.category}>
                    <h4 className="font-medium">{label(group.category)}</h4>
                    <div className="mt-2 space-y-2">
                      {group.items.map((item, index) => (
                        <div key={index} className="rounded-xl border border-white/10 p-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="text-sm font-medium">{item.requirement}</span>
                            <span className={`text-xs ${
                              item.assessment === "matched" ? "text-emerald-300"
                                : item.assessment === "partial" ? "text-amber-300" : "text-rose-300"
                            }`}>{label(item.assessment)}</span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-slate-300">{item.profile_evidence}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <details className="mt-5 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <summary className="cursor-pointer font-medium">View retrieved job description</summary>
              <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-slate-300">{active.job.description}</p>
            </details>
          </>
        )}

        <section className="mt-10 border-t border-white/10 pt-8">
          <h2 className="text-xl font-semibold">Previously analyzed jobs</h2>
          <div className="mt-4 space-y-3">
            {jobs.map(job => (
              <button
                key={job.id}
                onClick={() => { setSelected(job); setError(""); setMessage(""); }}
                className={`flex w-full items-center justify-between gap-4 rounded-xl border p-4 text-left hover:bg-white/[0.06] ${
                  selected?.id === job.id ? "border-cyan-300/40 bg-white/[0.06]" : "border-white/10 bg-white/[0.03]"
                }`}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{job.job.title}</span>
                  <span className="mt-1 block truncate text-sm text-slate-400">
                    {job.job.company} · {job.job.location || "Location not stated"}
                  </span>
                </span>
                <span className="shrink-0 text-xl font-semibold text-cyan-200">{job.match.score}%</span>
              </button>
            ))}
            {!jobs.length && <p className="text-sm text-slate-500">No jobs analyzed yet.</p>}
          </div>
        </section>
      </div>
    </main>
  );
}
