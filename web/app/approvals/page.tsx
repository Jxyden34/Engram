"use client";
import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

export default function ApprovalsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState("");

  function load() {
    api<any[]>("/api/v1/deletion-requests").then(setItems).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function act(id: string, action: "approve" | "reject") {
    try {
      await api(`/api/v1/deletion-requests/${id}/${action}`, {
        method: "POST",
        ...(action === "reject" ? { body: JSON.stringify({ reason: "Rejected from dashboard" }) } : {}),
      });
      load();
    } catch (e: any) { setError(e.message); }
  }

  return (
    <>
      <Topbar eyebrow="Human gate" title="Approval queue" />
      {error && <div className="errorBox">{error}</div>}
      <section className="panel" style={{ marginTop: 0 }}>
        <div className="tableWrap">
          <table>
            <thead><tr><th>Memory</th><th>Requested by</th><th>Reason</th><th>Status</th><th>Decision</th></tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.id}>
                  <td><strong>{x.title}</strong><div className="meta">{dateText(x.requested_at)}</div></td>
                  <td>{x.requested_by}</td>
                  <td>{x.reason}</td>
                  <td><span className={`badge ${x.status}`}>{x.status}</span></td>
                  <td>
                    {x.status === "pending" && (
                      <div className="row">
                        <button className="dangerButton" onClick={() => act(x.id, "approve")}>Approve delete</button>
                        <button className="ghostButton" onClick={() => act(x.id, "reject")}>Keep</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!items.length && <div className="empty">Nothing waiting for your decision.</div>}
      </section>
    </>
  );
}
