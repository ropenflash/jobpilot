import { getBackendHealth } from "@/lib/api";

export default async function Home() {
  const health = await getBackendHealth();

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <div className="mx-auto max-w-6xl">
        <header className="flex items-center justify-between border-b border-white/10 pb-6">
          <div>
            <div className="text-sm font-semibold tracking-[0.25em] text-cyan-300">JOBPILOT</div>
            <p className="mt-1 text-sm text-slate-400">Your job search, with you in control.</p>
          </div>
          <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs text-emerald-300">MVP · Milestone 3</span>
        </header>
        <section className="grid gap-10 py-12 md:grid-cols-[1.2fr_0.8fr]">
          <div>
            <p className="text-sm font-medium text-cyan-300">JOB APPLICATION COPILOT</p>
            <h1 className="mt-4 max-w-2xl text-4xl font-semibold leading-tight md:text-6xl">
              Spend less time applying. Keep control of every submission.
            </h1>
            <p className="mt-5 max-w-xl leading-7 text-slate-400">
              Analyze opportunities against your verified career profile, understand the evidence behind each match,
              and prepare applications while keeping control of every submission.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="/jobs" className="rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-slate-950">Analyze a job</a>
              <a href="/job-form-inspector" className="rounded-xl border border-cyan-300/40 px-5 py-3 text-cyan-200">Dual-agent form inspector</a>
              <a href="/profile" className="rounded-xl border border-white/15 px-5 py-3 text-slate-200">Career profile</a>
            </div>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl">
            <div className="text-sm text-slate-400">LOCAL SERVICES</div>
            <h2 className="mt-2 text-xl font-semibold">System health</h2>
            <div className="mt-6 space-y-3">
              <Status name="Spring Boot API" value={health.status} />
              <Status name="MongoDB" value={health.mongodb} />
              <Status name="Python worker" value="Check :8000/health" />
            </div>
            <p className="mt-6 text-xs leading-5 text-slate-500">
              Spring Boot and MongoDB health are checked by the backend. Python worker health is available at port 8000.
            </p>
          </div>
        </section>
        <section className="border-t border-white/10 py-10">
          <h2 className="text-2xl font-semibold">Your workspace</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <Milestone number="01" title="Foundation" description="Services, database connectivity and API skeleton." state="Complete" />
            <Milestone number="02" title="Resume intelligence" description="Upload a PDF, extract career facts and verify your profile." state="Complete" />
            <Milestone number="03" title="Job intelligence" description="Retrieve public Greenhouse postings, analyze requirements and compare with your verified profile." state="Now available" />
          </div>
        </section>
        <footer className="border-t border-white/10 py-6 text-xs text-slate-500">
          JobPilot · Local development MVP · Applications are never submitted without explicit approval.
        </footer>
      </div>
    </main>
  );
}

function Status({ name, value }: { name: string; value: string }) {
  const ok = value === "UP";
  return <div className="flex items-center justify-between rounded-xl bg-black/20 px-4 py-3">
    <span className="text-sm text-slate-300">{name}</span>
    <span className={`text-xs font-semibold ${ok ? "text-emerald-300" : "text-amber-300"}`}>{value}</span>
  </div>;
}

function Milestone({ number, title, description, state }: { number: string; title: string; description: string; state: string }) {
  return <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
    <div className="text-xs tracking-widest text-cyan-300">{number} / {state.toUpperCase()}</div>
    <h3 className="mt-3 text-lg font-semibold">{title}</h3>
    <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
  </article>;
}
