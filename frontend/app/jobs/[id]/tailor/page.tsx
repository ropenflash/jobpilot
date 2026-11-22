"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type Bullet = {
  text: string;
  source_refs: string[];
  source_evidence: string[];
};

type TailoredExperience = {
  source_index: number;
  company: string;
  title: string;
  location: string;
  start_date: string;
  end_date: string;
  technologies: string[];
  bullets: Bullet[];
};

type TailoredProject = {
  source_index: number;
  name: string;
  technologies: string[];
  bullets: Bullet[];
};

type TailoredResume = {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  target_title: string;
  target_company: string;
  target_headline: string;
  professional_summary: string;
  summary_source_refs: string[];
  summary_source_evidence: string[];
  skills: string[];
  experience: TailoredExperience[];
  projects: TailoredProject[];
  education: Record<string, string>[];
  certifications: string[];
  change_log: {
    section: string;
    change: string;
    rationale: string;
    source_refs: string[];
    source_evidence: string[];
  }[];
};

type TailoredResumeRecord = {
  id: string;
  jobId: string;
  jobTitle: string;
  company: string;
  profileResumeId: string;
  profileUpdatedAt: string;
  resume: TailoredResume;
  changeLog: TailoredResume["change_log"];
  createdAt: string;
  downloads: { pdf: string; docx: string };
};

type Job = {
  id: string;
  job: { title: string; company: string; location?: string };
};

function errorMessage(data: any, fallback: string) {
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

function sourceLabel(value: string) {
  return value.replaceAll(":", " ").replaceAll("_", " ");
}

function dateRange(item: TailoredExperience) {
  return [item.start_date, item.end_date].filter(Boolean).join(" - ");
}

function Evidence({ refs, evidence }: { refs: string[]; evidence: string[] }) {
  return (
    <details className="mt-2 rounded-lg bg-black/20 p-3">
      <summary className="cursor-pointer text-xs font-medium text-cyan-200">
        View source evidence ({refs.length} reference{refs.length === 1 ? "" : "s"})
      </summary>
      <div className="mt-3 space-y-3">
        {refs.map((ref, index) => (
          <div key={ref + index}>
            <div className="text-xs font-semibold text-slate-300">{sourceLabel(ref)}</div>
            <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-400">
              {evidence[index] ?? "Source text not available."}
            </p>
          </div>
        ))}
      </div>
    </details>
  );
}

export default function TailorResumePage() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;

  const [job, setJob] = useState<Job | null>(null);
  const [records, setRecords] = useState<TailoredResumeRecord[]>([]);
  const [selected, setSelected] = useState<TailoredResumeRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const [jobResponse, historyResponse] = await Promise.all([
          fetch(API + "/api/jobs/" + encodeURIComponent(jobId), { cache: "no-store" }),
          fetch(API + "/api/jobs/" + encodeURIComponent(jobId) + "/tailored-resumes", { cache: "no-store" }),
        ]);

        if (!jobResponse.ok) {
          const data = await jobResponse.json();
          throw new Error(errorMessage(data, "Could not load the analyzed job."));
        }
        const jobData: Job = await jobResponse.json();
        const history: TailoredResumeRecord[] = historyResponse.ok
          ? await historyResponse.json()
          : [];

        if (!active) return;
        setJob(jobData);
        setRecords(history);
        if (history.length) setSelected(history[0]);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Could not load this job.");
      } finally {
        if (active) setLoading(false);
      }
    }

    if (jobId) void load();
    return () => { active = false; };
  }, [jobId]);

  async function generate() {
    setGenerating(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(
        API + "/api/jobs/" + encodeURIComponent(jobId) + "/tailored-resumes",
        { method: "POST" },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessage(data, "Could not generate the tailored resume."));

      const record = data as TailoredResumeRecord;
      setSelected(record);
      setRecords(current => [record, ...current.filter(item => item.id !== record.id)]);
      setMessage("Tailored resume generated. Review every rewritten bullet and its source evidence before using it.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return <main className="min-h-screen px-6 py-10"><div className="mx-auto max-w-5xl text-slate-400">Loading job and resume history...</div></main>;
  }

  const resume = selected?.resume;

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <div className="mx-auto max-w-6xl">
        <a href="/jobs" className="text-sm text-cyan-300">← Back to jobs</a>

        <header className="mt-6">
          <div className="text-xs font-semibold tracking-[0.22em] text-cyan-300">RESUME TAILORING</div>
          <h1 className="mt-3 text-3xl font-semibold md:text-4xl">Prepare a role-specific resume</h1>
          {job && (
            <p className="mt-3 text-slate-400">
              {job.job.title} · {job.job.company}
              {job.job.location ? " · " + job.job.location : ""}
            </p>
          )}
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
            JobPilot will tailor the wording and ordering using your verified career profile.
            Employment details, dates, education and certifications are copied from the source profile.
            Your master profile will not be changed.
          </p>
        </header>

        <section className="mt-7 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <div>
            <h2 className="font-semibold">Generate tailored resume</h2>
            <p className="mt-1 text-sm text-slate-400">Creates an editable DOCX, a PDF and a source-linked change report.</p>
          </div>
          <button
            onClick={generate}
            disabled={generating}
            className="rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-slate-950 disabled:opacity-40"
          >
            {generating ? "Generating documents..." : records.length ? "Generate new version" : "Generate tailored resume"}
          </button>
        </section>

        {error && <div role="alert" className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-200">{error}</div>}
        {message && <div role="status" className="mt-5 rounded-xl border border-emerald-400/20 bg-emerald-400/10 p-4 text-sm text-emerald-200">{message}</div>}

        {records.length > 0 && (
          <section className="mt-7">
            <h2 className="text-lg font-semibold">Generated versions</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {records.map((record, index) => (
                <button
                  key={record.id}
                  onClick={() => { setSelected(record); setMessage(""); setError(""); }}
                  className={"rounded-xl border px-4 py-2 text-left text-sm " + (
                    selected?.id === record.id
                      ? "border-cyan-300/50 bg-cyan-300/10 text-cyan-100"
                      : "border-white/10 bg-white/[0.03] text-slate-300"
                  )}
                >
                  Version {records.length - index} · {new Date(record.createdAt).toLocaleString()}
                </button>
              ))}
            </div>
          </section>
        )}

        {resume && selected && (
          <>
            <section className="mt-7 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-xs tracking-wider text-slate-400">DOCUMENT PREVIEW</div>
                  <h2 className="mt-2 text-2xl font-semibold">{resume.full_name || "Candidate"}</h2>
                  <p className="mt-1 font-medium text-cyan-200">{resume.target_headline}</p>
                  <p className="mt-2 text-sm text-slate-400">
                    {[resume.email, resume.phone, resume.location].filter(Boolean).join(" · ")}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    Tailored for {selected.jobTitle} at {selected.company}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <a href={API + selected.downloads.docx} className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950">
                    Download DOCX
                  </a>
                  <a href={API + selected.downloads.pdf} className="rounded-lg border border-white/20 px-4 py-2 text-sm font-semibold text-slate-100">
                    Download PDF
                  </a>
                  <a href={"/jobs/" + encodeURIComponent(jobId) + "/apply"} className="rounded-lg border border-emerald-300/30 px-4 py-2 text-sm font-semibold text-emerald-200">
                    Continue to application
                  </a>
                </div>
              </div>

              <div className="mt-7 border-t border-white/10 pt-5">
                <h3 className="font-semibold">Professional summary</h3>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-300">{resume.professional_summary}</p>
                <Evidence refs={resume.summary_source_refs} evidence={resume.summary_source_evidence} />
              </div>

              <div className="mt-6">
                <h3 className="font-semibold">Core skills</h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  {resume.skills.map(skill => (
                    <span key={skill} className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">{skill}</span>
                  ))}
                  {!resume.skills.length && <span className="text-sm text-slate-500">No skills were selected from the profile.</span>}
                </div>
              </div>

              <div className="mt-7">
                <h3 className="font-semibold">Professional experience</h3>
                <div className="mt-3 space-y-5">
                  {resume.experience.map((item, index) => (
                    <article key={item.source_index} className="border-l-2 border-cyan-300/40 pl-4">
                      <div className="font-semibold">{item.title} · {item.company}</div>
                      <p className="mt-1 text-xs text-slate-500">
                        {[dateRange(item), item.location].filter(Boolean).join(" · ")}
                      </p>
                      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-300">
                        {item.bullets.map((bullet, bulletIndex) => (
                          <li key={bulletIndex}>
                            {bullet.text}
                            <Evidence refs={bullet.source_refs} evidence={bullet.source_evidence} />
                          </li>
                        ))}
                      </ul>
                      {item.technologies.length > 0 && (
                        <p className="mt-2 text-xs text-slate-500">Technologies: {item.technologies.join(", ")}</p>
                      )}
                    </article>
                  ))}
                </div>
              </div>

              {resume.projects.length > 0 && (
                <div className="mt-7">
                  <h3 className="font-semibold">Selected projects</h3>
                  <div className="mt-3 space-y-4">
                    {resume.projects.map(item => (
                      <article key={item.source_index} className="rounded-xl border border-white/10 p-4">
                        <h4 className="font-medium">{item.name}</h4>
                        <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-300">
                          {item.bullets.map((bullet, index) => (
                            <li key={index}>
                              {bullet.text}
                              <Evidence refs={bullet.source_refs} evidence={bullet.source_evidence} />
                            </li>
                          ))}
                        </ul>
                        {item.technologies.length > 0 && (
                          <p className="mt-2 text-xs text-slate-500">Technologies: {item.technologies.join(", ")}</p>
                        )}
                      </article>
                    ))}
                  </div>
                </div>
              )}

              {resume.education.length > 0 && (
                <div className="mt-7">
                  <h3 className="font-semibold">Education</h3>
                  {resume.education.map((item, index) => (
                    <p key={index} className="mt-2 text-sm text-slate-300">
                      {[item.degree, item.field_of_study, item.institution, item.graduation_year].filter(Boolean).join(" · ")}
                    </p>
                  ))}
                </div>
              )}

              {resume.certifications.length > 0 && (
                <div className="mt-7">
                  <h3 className="font-semibold">Certifications</h3>
                  <ul className="mt-2 list-disc pl-5 text-sm text-slate-300">
                    {resume.certifications.map((item, index) => <li key={index}>{item}</li>)}
                  </ul>
                </div>
              )}
            </section>

            <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
              <h2 className="text-lg font-semibold">What changed and why</h2>
              <p className="mt-1 text-sm text-slate-400">
                Each change includes the career-profile evidence used to support it.
              </p>
              <div className="mt-4 space-y-3">
                {selected.changeLog.map((item, index) => (
                  <article key={index} className="rounded-xl border border-white/10 p-4">
                    <div className="text-xs font-semibold uppercase tracking-wider text-cyan-200">{item.section}</div>
                    <p className="mt-2 text-sm font-medium text-slate-200">{item.change}</p>
                    <p className="mt-1 text-sm leading-6 text-slate-400">{item.rationale}</p>
                    {item.source_refs.length > 0 && (
                      <Evidence refs={item.source_refs} evidence={item.source_evidence} />
                    )}
                  </article>
                ))}
                {!selected.changeLog.length && <p className="text-sm text-slate-500">No change notes were returned.</p>}
              </div>
            </section>

            <p className="mt-5 text-xs leading-5 text-amber-200">
              Review before sending. AI wording can still overstate a source fact even when it includes a reference.
              Check every bullet, metric and skill against your actual experience.
            </p>
          </>
        )}

        {!records.length && !generating && (
          <div className="mt-8 rounded-2xl border border-dashed border-white/15 p-8 text-center">
            <h2 className="font-semibold">No tailored versions yet</h2>
            <p className="mt-2 text-sm text-slate-400">
              Generate the first version to see the role-specific resume preview and source-linked edits here.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
