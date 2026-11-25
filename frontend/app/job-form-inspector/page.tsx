"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type Field = {
  field?: string;
  label?: string;
  input_type?: string;
  required?: boolean | null;
  evidence?: string;
  confidence?: string;
  visible_value?: string | null;
};

type AgentResult = {
  agent?: string;
  source?: string;
  status?: string;
  fields?: Field[];
  instructions?: string[];
  limitations?: string[];
  visible_text?: string[];
  page_title?: string | null;
  screenshots_captured?: number;
  note?: string | null;
};

type InspectionResult = {
  job: { title: string; company: string; location?: string | null; job_url: string };
  agents: { html: AgentResult; visual: AgentResult };
  comparison: {
    shared_fields: string[];
    html_only_fields: string[];
    visual_only_fields: string[];
    field_count: number;
  };
};

function responseMessage(data: any) {
  const detail = data?.detail;
  if (typeof detail === "string") {
    try { return JSON.parse(detail).detail ?? detail; } catch { return detail; }
  }
  return data?.message ?? "Could not inspect this job.";
}

function AgentCard({ title, subtitle, result }: { title: string; subtitle: string; result?: AgentResult }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
      <div className="text-xs font-semibold tracking-[0.18em] text-cyan-300">{subtitle}</div>
      <h2 className="mt-2 text-xl font-semibold">{title}</h2>
      <div className="mt-2 text-xs text-slate-500">{result?.source ?? "Waiting for result"}</div>

      <h3 className="mt-6 font-semibold">Detected fields ({result?.fields?.length ?? 0})</h3>
      {result?.fields?.length ? (
        <div className="mt-3 space-y-3">
          {result.fields.map((field, index) => (
            <article key={index} className="rounded-xl border border-white/10 bg-black/20 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{field.label || field.field || "Unnamed field"}</span>
                <span className="text-xs text-cyan-200">{field.input_type || field.confidence || "Unspecified"}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full bg-white/10 px-2 py-1">
                  Required: {field.required === null || field.required === undefined ? "Not stated" : field.required ? "Yes" : "No"}
                </span>
                {field.field && <span className="rounded-full bg-white/10 px-2 py-1">{field.field}</span>}
              </div>
              {field.evidence && <p className="mt-2 text-sm leading-6 text-slate-400">{field.evidence}</p>}
            </article>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No fields detected, or this agent did not return a result.</p>
      )}

      {!!result?.instructions?.length && (
        <>
          <h3 className="mt-6 font-semibold">Instructions</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
            {result.instructions.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </>
      )}

      {!!result?.visible_text?.length && (
        <>
          <h3 className="mt-6 font-semibold">Visible page text</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
            {result.visible_text.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </>
      )}

      {!!result?.limitations?.length && (
        <>
          <h3 className="mt-6 font-semibold">Limitations</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-200">
            {result.limitations.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </>
      )}
      {result?.note && <p className="mt-4 text-xs text-amber-200">{result.note}</p>}
    </section>
  );
}

export default function JobFormInspectorPage() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<InspectionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function inspect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch(`${API}/api/jobs/inspect-form`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data));
      setResult(data as InspectionResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inspection failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <div className="mx-auto max-w-7xl">
        <a href="/" className="text-sm text-cyan-300">← Dashboard</a>
        <header className="mt-6">
          <div className="text-xs font-semibold tracking-[0.22em] text-cyan-300">DUAL-AGENT INSPECTION</div>
          <h1 className="mt-3 text-3xl font-semibold md:text-4xl">Job form inspector</h1>
          <p className="mt-3 max-w-3xl leading-7 text-slate-400">
            Paste a public Greenhouse job URL. The HTML agent extracts form-related requirements
            from source content, while the visual agent examines Playwright screenshots. Compare
            their findings independently; neither agent fills or submits an application.
          </p>
        </header>

        <form onSubmit={inspect} className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <label htmlFor="job-url" className="block text-sm text-slate-300">Greenhouse job URL</label>
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
              disabled={loading || !url.trim()}
              className="rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-slate-950 disabled:opacity-40"
            >
              {loading ? "Running both agents…" : "Inspect job form"}
            </button>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            This first version supports public Greenhouse postings. The visual result only covers the
            captured job page screenshots; it does not navigate into an application form.
          </p>
        </form>

        {error && <div role="alert" className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-200">{error}</div>}

        {result && (
          <>
            <section className="mt-6 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
              <div className="text-xs tracking-wider text-slate-500">JOB</div>
              <h2 className="mt-2 text-2xl font-semibold">{result.job.title}</h2>
              <p className="mt-1 text-slate-300">{result.job.company} · {result.job.location || "Location not stated"}</p>
              <a className="mt-3 inline-block text-sm text-cyan-300 underline" href={result.job.job_url} target="_blank" rel="noreferrer">
                Open original posting ↗
              </a>
              <div className="mt-4 grid gap-3 sm:grid-cols-4">
                <Metric label="Total unique fields" value={result.comparison.field_count} />
                <Metric label="Both agents found" value={result.comparison.shared_fields.length} />
                <Metric label="HTML only" value={result.comparison.html_only_fields.length} />
                <Metric label="Visual only" value={result.comparison.visual_only_fields.length} />
              </div>
            </section>

            <section className="mt-5 grid gap-5 lg:grid-cols-2">
              <AgentCard title="HTML requirements agent" subtitle="AGENT 01 · STRUCTURED SOURCE" result={result.agents.html} />
              <AgentCard title="Playwright visual agent" subtitle="AGENT 02 · SCREENSHOT EVIDENCE" result={result.agents.visual} />
            </section>

            <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
              <h2 className="text-lg font-semibold">Agent comparison</h2>
              <p className="mt-1 text-sm text-slate-400">Field names are normalized before comparing the two independent outputs.</p>
              <ComparisonList title="Detected by both agents" values={result.comparison.shared_fields} />
              <ComparisonList title="Found only by HTML agent" values={result.comparison.html_only_fields} />
              <ComparisonList title="Found only by visual agent" values={result.comparison.visual_only_fields} />
            </section>
          </>
        )}
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-black/20 p-4">
    <div className="text-2xl font-semibold tabular-nums">{value}</div>
    <div className="mt-1 text-xs text-slate-500">{label}</div>
  </div>;
}

function ComparisonList({ title, values }: { title: string; values: string[] }) {
  return <div className="mt-5">
    <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
    {values.length ? (
      <div className="mt-2 flex flex-wrap gap-2">
        {values.map(value => <span key={value} className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">{value}</span>)}
      </div>
    ) : <p className="mt-2 text-sm text-slate-500">None</p>}
  </div>;
}
