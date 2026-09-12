"use client";
import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

export default function AuditPage() {
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    api<any[]>("/api/v1/audit?limit=250").then(setItems).catch(() => {});
  }, []);

  return (
    <>
      <Topbar eyebrow="Immutable-ish receipts" title="Audit trail" />
      <section className="panel" style={{ marginTop: 0 }}>
        <div className="tableWrap">
          <table>
            <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Reason</th></tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.id}>
                  <td className="meta">{dateText(x.created_at)}</td>
                  <td>{x.actor}</td>
                  <td><span className="badge">{x.action}</span></td>
                  <td>{x.entity_type}{x.entity_id ? ` · ${x.entity_id.slice(0, 8)}` : ""}</td>
                  <td className="meta">{x.reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!items.length && <div className="empty">Audit events will appear here.</div>}
      </section>
    </>
  );
}
