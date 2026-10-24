"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export default function ArchiveMemoryControl({ memory, onChange }: {
  memory: { id: string; archived_at?: string | null; updated_at: string }; onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const reason = String(new FormData(e.currentTarget).get("reason") || "");
    setBusy(true); setError("");
    try {
      await api(`/api/v1/memories/${memory.id}/archive`, { method: "POST", body: JSON.stringify({
        archived: !memory.archived_at, expected_updated_at: memory.updated_at, reason,
      }) });
      onChange();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <section className="panel">
    <h2>{memory.archived_at ? "Archived memory" : "Archive this memory"}</h2>
    <p className="meta">Archiving excludes this memory from default search and AI context. Its content and history stay available; you can restore it here.</p>
    <form onSubmit={submit} className="row">
      <label htmlFor="archive-reason">Reason</label>
      <input id="archive-reason" className="input" name="reason" required minLength={3} maxLength={1000} placeholder="Why change its archival state?" />
      <button className="button" disabled={busy}>{busy ? "Saving…" : memory.archived_at ? "Restore memory" : "Archive memory"}</button>
    </form>
    {error && <p className="errorBox" role="alert">{error}</p>}
  </section>;
}
