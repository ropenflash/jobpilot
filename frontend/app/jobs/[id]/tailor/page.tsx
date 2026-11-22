"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type ResumeStyle = "classic" | "modern" | "compact";

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
  resumeStyle?: ResumeStyle;
  profileResumeId: string;
  profileUpdatedAt: string;
  resume: TailoredResume;
  changeLog: TailoredResume["change_log"];
  createdAt: string;
  downloads: { pdf: string; docx: string };
};

type MasterExperience = {
  company?: string | null;
  title?: string | null;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  description?: string | null;
  technologies?: string[];
};

type MasterProject = {
  name?: string | null;
  description?: string | null;
  technologies?: string[];
};

type MasterProfile = {
  full_name?: string | null;
  headline?: string | null;
  professional_summary?: string | null;
  skills?: string[];
  experience?: MasterExperience[];
  projects?: MasterProject[];
  education?: Record<string, string>[];
  certifications?: string[];
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
  const [selectedStyle, setSelectedStyle] = useState<ResumeStyle>("classic");
  const [masterProfile, setMasterProfile] = useState<MasterProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const [jobResponse, historyResponse, profileResponse] = await Promise.all([
          fetch(API + "/api/jobs/" + encodeURIComponent(jobId), { cache: "no-store" }),
          fetch(API + "/api/jobs/" + encodeURIComponent(jobId) + "/tailored-resumes", { cache: "no-store" }),
          fetch(API + "/api/profile", { cache: "no-store" }),
        ]);

        if (!jobResponse.ok) {
          const data = await jobResponse.json();
          throw new Error(errorMessage(data, "Could not load the analyzed job."));
        }
        const jobData: Job = await jobResponse.json();
        const history: TailoredResumeRecord[] = historyResponse.ok
          ? await historyResponse.json()
          : [];
        const profileData = profileResponse.ok ? await profileResponse.json() : null;
        const sourceProfile = profileData?.configured ? profileData.profile as MasterProfile : null;

        if (!active) return;
        setJob(jobData);
        setMasterProfile(sourceProfile);
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
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ style: selectedStyle }),
        },
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

        <section className="mt-7 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="font-semibold">Choose a resume design</h2>
              <p className="mt-1 max-w-2xl text-sm text-slate-400">
                The tailored content stays the same; the typography, spacing and visual hierarchy change.
                Each generated version includes both PDF and editable Word files.
              </p>
            </div>
            <button
              onClick={generate}
              disabled={generating}
              className="rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-slate-950 disabled:opacity-40"
            >
              {generating ? "Generating documents..." : records.length ? "Generate new version" : "Generate tailored resume"}
            </button>
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {([
              { value: "classic", title: "ATS Classic", description: "Conventional, restrained and highly scannable." },
              { value: "modern", title: "Modern Professional", description: "Left-aligned header with stronger visual hierarchy." },
              { value: "compact", title: "Compact Executive", description: "Tighter spacing for information-dense profiles." },
            ] as { value: ResumeStyle; title: string; description: string }[]).map(option => (
              <button
                key={option.value}
                type="button"
                aria-pressed={selectedStyle === option.value}
                onClick={() => setSelectedStyle(option.value)}
                className={"rounded-xl border p-4 text-left transition " + (
                  selectedStyle === option.value
                    ? "border-cyan-300/60 bg-cyan-300/10"
                    : "border-white/10 bg-black/10 hover:border-white/25"
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{option.title}</span>
                  <span className={"h-4 w-4 rounded-full border " + (
                    selectedStyle === option.value ? "border-cyan-200 bg-cyan-200 ring-2 ring-cyan-200/20" : "border-slate-500"
                  )} />
                </span>
                <span className="mt-2 block text-xs leading-5 text-slate-400">{option.description}</span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">Choose the style before generating. Older saved versions retain their original style.</p>
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
                  onClick={() => {
                    setSelected(record);
                    setSelectedStyle(record.resumeStyle ?? "classic");
                    setMessage("");
                    setError("");
                  }}
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
                  <div className="text-xs tracking-wider text-slate-400">
                    DOCUMENT PREVIEW · {({ classic: "ATS Classic", modern: "Modern Professional", compact: "Compact Executive" } as Record<ResumeStyle, string>)[selected.resumeStyle ?? "classic"]}
                  </div>
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
                    Download Word (.docx)
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
                <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <h3 className="text-xl font-semibold">Side-by-side resume comparison</h3>
                    <p className="mt-1 text-sm text-slate-400">
                      Master profile on the left · generated, job-targeted version on the right
                    </p>
                  </div>
                  <span className="text-xs text-slate-500">Read-only · master profile stays unchanged</span>
                </div>

                {!masterProfile && (
                  <div className="mb-4 rounded-xl border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100">
                    The master profile could not be loaded. Check that your original resume is uploaded and saved in Profile.
                  </div>
                )}

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <article className="min-w-0 rounded-2xl border border-white/10 bg-black/20 p-5">
                    <div className="mb-5 border-b border-white/10 pb-4">
                      <div className="text-xs font-semibold tracking-[0.18em] text-slate-400">MASTER RESUME</div>
                      <h3 className="mt-2 text-xl font-semibold">{masterProfile?.full_name || resume.full_name || "Candidate"}</h3>
                      <p className="mt-1 text-sm text-slate-400">{masterProfile?.headline || "Original profile headline"}</p>
                      <p className="mt-2 text-xs text-slate-500">Original profile facts and descriptions</p>
                    </div>

                    <div className="space-y-6">
                      <div>
                        <h4 className="font-semibold">Professional summary</h4>
                        <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                          {masterProfile?.professional_summary || "No summary in the saved master profile."}
                        </p>
                      </div>

                      <div>
                        <h4 className="font-semibold">Skills</h4>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {(masterProfile?.skills ?? []).map(skill => (
                            <span key={skill} className="rounded-full bg-white/10 px-2.5 py-1 text-xs text-slate-300">{skill}</span>
                          ))}
                          {!masterProfile?.skills?.length && <span className="text-sm text-slate-500">No skills recorded.</span>}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold">Professional experience</h4>
                        <div className="mt-3 space-y-4">
                          {(masterProfile?.experience ?? []).map((item, index) => (
                            <div key={index} className="rounded-xl border border-white/10 p-3">
                              <div className="font-medium">{item.title || "Role"} · {item.company || "Company not listed"}</div>
                              <p className="mt-1 text-xs text-slate-500">
                                {[
                                  [item.start_date, item.end_date].filter(Boolean).join(" - "),
                                  item.location
                                ].filter(Boolean).join(" · ")}
                              </p>
                              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                                {item.description || "No original description recorded."}
                              </p>
                              {!!item.technologies?.length && (
                                <p className="mt-2 text-xs text-slate-500">Technologies: {item.technologies.join(", ")}</p>
                              )}
                            </div>
                          ))}
                          {!masterProfile?.experience?.length && <p className="text-sm text-slate-500">No work history recorded.</p>}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold">Projects</h4>
                        <div className="mt-3 space-y-3">
                          {(masterProfile?.projects ?? []).map((item, index) => (
                            <div key={index} className="rounded-xl border border-white/10 p-3">
                              <div className="font-medium">{item.name || "Project"}</div>
                              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                                {item.description || "No original description recorded."}
                              </p>
                              {!!item.technologies?.length && (
                                <p className="mt-2 text-xs text-slate-500">Technologies: {item.technologies.join(", ")}</p>
                              )}
                            </div>
                          ))}
                          {!masterProfile?.projects?.length && <p className="text-sm text-slate-500">No projects recorded.</p>}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold">Education</h4>
                        <div className="mt-2 space-y-2">
                          {(masterProfile?.education ?? []).map((item, index) => (
                            <p key={index} className="text-sm leading-6 text-slate-300">
                              {[item.degree, item.field_of_study, item.institution, item.graduation_year].filter(Boolean).join(" · ")}
                            </p>
                          ))}
                          {!masterProfile?.education?.length && <p className="text-sm text-slate-500">No education recorded.</p>}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold">Certifications</h4>
                        <div className="mt-2 space-y-1">
                          {(masterProfile?.certifications ?? []).map((item, index) => (
                            <p key={index} className="text-sm text-slate-300">{item}</p>
                          ))}
                          {!masterProfile?.certifications?.length && <p className="text-sm text-slate-500">No certifications recorded.</p>}
                        </div>
                      </div>
                    </div>
                  </article>

                  <article className="min-w-0 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.035] p-5">
                    <div className="mb-5 border-b border-white/10 pb-4">
                      <div className="text-xs font-semibold tracking-[0.18em] text-cyan-200">GENERATED RESUME</div>
                      <h3 className="mt-2 text-xl font-semibold">{resume.full_name || "Candidate"}</h3>
                      <p className="mt-1 text-sm font-medium text-cyan-100">{resume.target_headline}</p>
                      <p className="mt-2 text-xs text-slate-500">Tailored for {selected.jobTitle} at {selected.company}</p>
                    </div>

                    <div className="space-y-6">
                      <div>
                        <h4 className="font-semibold">Professional summary</h4>
                        <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">{resume.professional_summary}</p>
                        <Evidence refs={resume.summary_source_refs} evidence={resume.summary_source_evidence} />
                      </div>

                      <div>
                        <h4 className="font-semibold">Skills selected for this role</h4>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {resume.skills.map(skill => (
                            <span key={skill} className="rounded-full bg-cyan-300/10 px-2.5 py-1 text-xs text-cyan-100">{skill}</span>
                          ))}
                          {!resume.skills.length && <span className="text-sm text-slate-500">No skills selected.</span>}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold">Professional experience</h4>
                        <div className="mt-3 space-y-4">
                          {resume.experience.map(item => (
                            <div key={item.source_index} className="rounded-xl border border-white/10 p-3">
                              <div className="font-medium">{item.title} · {item.company}</div>
                              <p className="mt-1 text-xs text-slate-500">
                                {[dateRange(item), item.location].filter(Boolean).join(" · ")}
                              </p>
                              <div className="mt-3 space-y-3">
                                {item.bullets.map((bullet, index) => (
                                  <div key={index}>
                                    <p className="text-sm leading-6 text-slate-200">{bullet.text}</p>
                                    <Evidence refs={bullet.source_refs} evidence={bullet.source_evidence} />
                                  </div>
                                ))}
                              </div>
                              {!!item.technologies.length && (
                                <p className="mt-2 text-xs text-slate-500">Technologies: {item.technologies.join(", ")}</p>
                              )}
                            </div>
                          ))}
                          {!resume.experience.length && <p className="text-sm text-slate-500">No experience selected.</p>}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold">Selected projects</h4>
                        <div className="mt-3 space-y-3">
                          {resume.projects.map(item => (
                            <div key={item.source_index} className="rounded-xl border border-white/10 p-3">
                              <div className="font-medium">{item.name}</div>
                              <div className="mt-2 space-y-3">
                                {item.bullets.map((bullet, index) => (
                                  <div key={index}>
                                    <p className="text-sm leading-6 text-slate-200">{bullet.text}</p>
                                    <Evidence refs={bullet.source_refs} evidence={bullet.source_evidence} />
                                  </div>
                                ))}
                              </div>
                              {!!item.technologies.length && (
                                <p className="mt-2 text-xs text-slate-500">Technologies: {item.technologies.join(", ")}</p>
                              )}
                            </div>
                          ))}
                          {!resume.projects.length && <p className="text-sm text-slate-500">No projects selected.</p>}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold">Education</h4>
                        <div className="mt-2 space-y-2">
                          {resume.education.map((item, index) => (
                            <p key={index} className="text-sm leading-6 text-slate-300">
                              {[item.degree, item.field_of_study, item.institution, item.graduation_year].filter(Boolean).join(" · ")}
                            </p>
                          ))}
                          {!resume.education.length && <p className="text-sm text-slate-500">No education included.</p>}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold">Certifications</h4>
                        <div className="mt-2 space-y-1">
                          {resume.certifications.map((item, index) => (
                            <p key={index} className="text-sm text-slate-300">{item}</p>
                          ))}
                          {!resume.certifications.length && <p className="text-sm text-slate-500">No certifications included.</p>}
                        </div>
                      </div>
                    </div>
                  </article>
                </div>
              </div>

              <p className="mt-6 border-t border-white/10 pt-5 text-xs leading-5 text-amber-200">
                Review before sending. AI wording can still overstate a source fact even when it includes a reference.
                Check every claim, metric and skill against your actual experience.
              </p>
            </section>

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
