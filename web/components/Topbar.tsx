"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function Topbar({ eyebrow, title }: { eyebrow: string; title: string }) {
  const [unread, setUnread] = useState(0);
  const [admin, setAdmin] = useState(false);
  const [user, setUser] = useState<string>("");

  useEffect(() => {
    api<any>("/api/v1/auth/me")
      .then((v) => {
        setUser(v.username || v.actor);
        setAdmin(v.is_admin);
        if (v.is_admin) api<{ unread: number }>("/api/v1/notifications").then(inbox => setUnread(inbox.unread)).catch(() => {});
      })
      .catch(() => {});
  }, []);

  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
      </div>
      <div className="row">
        {admin && <Link className="ghostButton" href="/notifications">Notifications{unread > 0 ? " (" + unread + ")" : ""}</Link>}
      <div className="userChip">
        <span className="pulse" />
        {user || "authenticated"}
      </div></div>
    </header>
  );
}
