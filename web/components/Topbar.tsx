"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function Topbar({ eyebrow, title }: { eyebrow: string; title: string }) {
  const [user, setUser] = useState<string>("");

  useEffect(() => {
    api<any>("/api/v1/auth/me")
      .then((v) => setUser(v.username || v.actor))
      .catch(() => {});
  }, []);

  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
      </div>
      <div className="userChip">
        <span className="pulse" />
        {user || "authenticated"}
      </div>
    </header>
  );
}
