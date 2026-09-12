"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode } from "react";
import { api } from "@/lib/api";

const links = [
  ["/", "Overview", "◈"],
  ["/memories", "Memories", "◎"],
  ["/documents", "Documents", "▱"],
  ["/imports", "Memory Inbox", "✦"],
  ["/connectors", "Connectors", "⇄"],
  ["/knowledge", "Knowledge Graph", "◎"],
  ["/timeline", "Timeline", "◷"],
  ["/health", "Memory Health", "♡"],
  ["/approvals", "Approvals", "◇"],
  ["/audit", "Audit trail", "⌁"],
  ["/settings", "AI & API", "⌘"],
];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  if (pathname === "/login") return <>{children}</>;

  async function logout() {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } finally {
      router.push("/login");
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark">M</div>
          <div>
            <strong>MemoryBank</strong>
            <span>private cognition layer</span>
          </div>
        </div>

        <nav>
          {links.map(([href, label, icon]) => (
            <Link
              key={href}
              href={href}
              className={
                pathname === href || (href !== "/" && pathname.startsWith(href))
                  ? "navLink active"
                  : "navLink"
              }
            >
              <span className="navIcon">{icon}</span>
              {label}
            </Link>
          ))}
        </nav>

        <div className="sidebarFoot">
          <div className="secureDot"><i /> Encrypted edge</div>
          <button className="ghostButton" onClick={logout}>Sign out</button>
        </div>
      </aside>

      <main className="main">{children}</main>
    </div>
  );
}
