"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

export default function Dashboard() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api("/api/v1/stats").then(setData).catch(() => {});
  }, []);

  const maxType = Math.max(1, ...(data?.types || []).map((x: any) => Number(x.count)));

  return (
    <>
      <Topbar eyebrow="System overview" title="Your memory, mapped." />

      <div className="grid4">
        {[
          ["Memories", data?.memories ?? "—", "active knowledge objects"],
          ["Documents", data?.documents ?? "—", "source files"],
          ["Approvals", data?.pending_deletions ?? "—", "waiting for you"],
          ["AI keys", data?.api_keys ?? "—", "active integrations"],
        ].map(([label, value, hint]) => (
          <div className="statCard" key={String(label)}>
            <div className="statLabel">{label}</div>
            <div className="statValue">{value}</div>
            <div className="statHint">{hint}</div>
          </div>
        ))}
      </div>

      <div className="split">
        <section className="panel">
          <div className="panelHead">
            <h2>Recently touched memories</h2>
            <Link className="ghostButton" href="/memories">Open memory graph</Link>
          </div>
          <div className="tableWrap">
            <table>
              <thead><tr><th>Memory</th><th>Type</th><th>Weight</th><th>Updated</th></tr></thead>
              <tbody>
                {(data?.recent || []).map((m: any) => (
                  <tr key={m.id}>
                    <td><Link href={`/memories/${m.id}`}><strong>{m.title}</strong></Link></td>
                    <td><span className="badge">{m.memory_type}</span></td>
                    <td>{m.importance}/10</td>
                    <td className="meta">{dateText(m.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && !data.recent?.length && <div className="empty">No memories yet. Time to give the vault a pulse.</div>}
        </section>

        <section className="panel">
          <div className="panelHead"><h2>Memory topology</h2><span className="meta">by type</span></div>
          <div className="typeBars">
            {(data?.types || []).map((x: any) => (
              <div className="typeBar" key={x.memory_type}>
                <span>{x.memory_type}</span>
                <div className="track"><div className="fill" style={{ width: `${(x.count / maxType) * 100}%` }} /></div>
                <span>{x.count}</span>
              </div>
            ))}
          </div>
          {data && !data.types?.length && <div className="empty">Your topology appears after the first memory.</div>}
        </section>
      </div>
    </>
  );
}
