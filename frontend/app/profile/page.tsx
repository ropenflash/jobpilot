"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";
type ProfileData = Record<string, any>;

export default function ProfilePage() {
  const [file, setFile] = useState<File | null>(null);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [verified, setVerified] = useState(false);

  async function loadProfile() {
    try {
      const res = await fetch(`${API}/api/profile`);
      const data = await res.json();
      if (data.configured) {
        setProfile(data.profile);
        setVerified(data.verified);
      }
    } catch {
      setMessage("Could not reach backend. Check Spring Boot.");
    }
  }

  useEffect(() => { void loadProfile(); }, []);

  async function upload() {
    if (!file) return;
    setLoading(true);
    setMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/api/resumes`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? data.message ?? "Resume upload failed");
      setProfile(data.profile);
      setVerified(false);
      setMessage("Resume parsed. Review every field and save your verified profile.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    if (!profile) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Could not save profile");
      setVerified(true);
      setMessage("Career profile saved and marked as verified.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Save failed");
    } finally {
      setLoading(false);
    }
  }

  function update(key: string, value: string | string[]) {
    setProfile(current => current ? { ...current, [key]: value } : current);
    setVerified(false);
  }

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <div className="mx-auto max-w-4xl">
        <a href="/" className="text-sm text-cyan-300">← Dashboard</a>
        <h1 className="mt-6 text-3xl font-semibold">Career profile</h1>
        <p className="mt-2 text-slate-400">
          Upload your PDF resume. AI extracts career facts for your review.
          Nothing is verified until you confirm it.
        </p>

        <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
          <h2 className="text-lg font-semibold">Upload master resume</h2>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <input type="file" accept="application/pdf,.pdf"
              onChange={event => setFile(event.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-lg file:border-0 file:bg-cyan-300 file:px-4 file:py-2 file:font-semibold file:text-slate-950" />
            <button disabled={!file || loading} onClick={upload}
              className="rounded-xl bg-cyan-300 px-5 py-2 font-semibold text-slate-950 disabled:opacity-40">
              {loading ? "Working..." : "Upload and analyze"}
            </button>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            PDF only · Maximum 5 MB · Text-based PDFs supported. Scanned PDFs need OCR.
          </p>
        </section>

        {message && <p className="mt-5 rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-slate-200">{message}</p>}

        {profile && <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Extracted information</h2>
            <span className={`rounded-full px-3 py-1 text-xs ${verified ? "bg-emerald-400/10 text-emerald-300" : "bg-amber-400/10 text-amber-300"}`}>
              {verified ? "Verified by you" : "Needs your review"}
            </span>
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {(["full_name", "email", "phone", "location", "headline", "total_experience_years"] as const).map(key => (
              <label key={key} className="text-sm capitalize text-slate-400">
                {key.replaceAll("_", " ")}
                <input value={profile[key] ?? ""}
                  onChange={event => update(key, event.target.value)}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300" />
              </label>
            ))}
          </div>

          <label className="mt-4 block text-sm text-slate-400">Professional summary
            <textarea value={profile.professional_summary ?? ""}
              onChange={event => update("professional_summary", event.target.value)}
              rows={4}
              className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300" />
          </label>

          <label className="mt-4 block text-sm text-slate-400">Skills (comma separated)
            <input value={(profile.skills ?? []).join(", ")}
              onChange={event => update("skills", event.target.value.split(",").map(s => s.trim()).filter(Boolean))}
              className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300" />
          </label>

          <div className="mt-5">
            <h3 className="font-medium">Experience extracted</h3>
            <div className="mt-2 space-y-3">
              {(profile.experience ?? []).map((item: any, index: number) => (
                <div key={index} className="rounded-xl border border-white/10 p-4">
                  <div className="font-medium">{item.title || "Untitled role"} · {item.company || "Company not detected"}</div>
                  <p className="mt-1 text-xs text-slate-400">{item.start_date || "?"} – {item.end_date || "?"}</p>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-slate-300">{item.description || "No description extracted"}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-5">
            <h3 className="font-medium">Education</h3>
            {(profile.education ?? []).map((item: any, index: number) => (
              <p key={index} className="mt-2 text-sm text-slate-300">
                {item.degree} · {item.institution} · {item.graduation_year}
              </p>
            ))}
          </div>

          {!!(profile.extraction_notes ?? []).length && <div className="mt-5 rounded-xl bg-amber-400/10 p-4 text-sm text-amber-200">
            <strong>Review notes</strong>
            <ul className="mt-2 list-disc pl-5">
              {profile.extraction_notes.map((note: string, index: number) => <li key={index}>{note}</li>)}
            </ul>
          </div>}

          <button disabled={loading} onClick={save}
            className="mt-6 rounded-xl bg-emerald-300 px-5 py-3 font-semibold text-slate-950 disabled:opacity-40">
            {loading ? "Saving..." : "Save and verify profile"}
          </button>
        </section>}
      </div>
    </main>
  );
}
