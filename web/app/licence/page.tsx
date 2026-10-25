"use client";
import { useEffect, useState, FormEvent } from "react";
import { api } from "@/lib/api";

export default function LicencePage() {
  const [edition, setEdition] = useState<any>(null);
  const [key, setKey] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  useEffect(() => { api("/api/v1/edition").then(setEdition).catch(e => setMessage(e.message)); }, []);
  async function activate(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try { await api("/api/v1/license", {method:"PUT",body:JSON.stringify({mode:"commercial",license_key:key.trim()})}); window.location.assign("/"); }
    catch(e: any) { setMessage(e.message); } finally { setBusy(false); }
  }
  const purchase = edition?.purchase_url ? `${edition.purchase_url}${edition.purchase_url.includes("?") ? "&" : "?"}installation_id=${encodeURIComponent(edition.installation_id)}` : "mailto:jayden@hindley.tech";
  return <main className="licencePage"><a className="licenceBrand" href="/">â—ˆ Engram</a><div className="licenceGrid"><section><p className="licenceEyebrow">YOUR PRIVATE COGNITION LAYER</p><h1>Make room<br/>for whatâ€™s next.</h1><p className="licenceLead">Memories, projects and intelligence.<br/>One private space, built around you.</p><p className="licenceFine">Your data stays with your installation. Commercial activation uses a signed key and does not require an online licence check.</p></section><section className="licenceCard"><span className="badge">{edition ? edition.edition === "community" ? "PERSONAL / FREE" : edition.locked ? "COMMERCIAL / ACTIVATION REQUIRED" : "COMMERCIAL / ACTIVE" : "CHECKING EDITION"}</span><h2>{edition?.edition === "community" ? "Free to make it yours." : edition?.locked === false ? "Youâ€™re ready to work." : "Activate your workspace."}</h2>{edition?.edition === "community" ? <><p>Personal use is free. Business, workplace and commercial use require the Commercial build and a paid key.</p><a className="button" href="/">Open Engram</a></> : edition && <><p>{edition.locked ? "You need to buy a licence key to use Engram Commercial." : "Your licence is active. You can replace it below when renewing."}</p><label className="licenceId">Installation ID<code>{edition.installation_id}</code></label><button className="ghostButton" onClick={async()=>{try{await navigator.clipboard.writeText(edition.installation_id);setMessage("Installation ID copied.");}catch{setMessage("Select and copy the installation ID above.");}}}>Copy installation ID</button><form onSubmit={activate}><label htmlFor="licence-key">Licence key</label><input id="licence-key" type={show ? "text" : "password"} value={key} onChange={e=>setKey(e.target.value)} placeholder="ENGRAM-C1.â€¦" maxLength={8192} autoComplete="off" spellCheck={false} required disabled={busy}/><label className="licenceShow"><input type="checkbox" checked={show} onChange={e=>setShow(e.target.checked)}/>Show key</label><button className="button" disabled={busy}>{busy ? "Activatingâ€¦" : "Activate licence"}</button></form><p className="licenceFine">Sign in as an administrator to activate. <a href="/login">Sign in</a></p><hr/><a className="button" href={purchase}>Buy a licence key â†—</a><p className="licenceFine">Request a key, arrange payment with the owner, then receive your key by email. No payment is taken here.</p>{!edition.locked && <a href="/">Return to workspace â†’</a>}</>}{edition?.expires_at&&<div><p>Expires {new Date(edition.expires_at).toLocaleString()}</p><a className="ghostButton" href={`${purchase}${purchase.includes('?')?'&':'?'}renewal=1`}>Request renewal</a></div>}{message && <p role="status" className="errorBox">{message}</p>}</section></div></main>;
}
