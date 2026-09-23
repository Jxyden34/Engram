"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";

const links = [
  ["/", "Overview", "◈"],
  ["/memories", "Memories", "◎"],
  ["/documents", "Documents", "▱"],
  ["/projects", "Projects", "▦"],
  ["/agent", "Memory Agent", "✧"],
  ["/imports", "Memory Inbox", "✦"],
  ["/connectors", "Connectors", "⇄"],
  ["/knowledge", "Knowledge Graph", "◎"],
  ["/timeline", "Timeline", "◷"],
  ["/health", "Memory Health", "♡"],
  ["/disaster-recovery", "Disaster Recovery", "⛨"],
  ["/approvals", "Approvals", "◇"],
  ["/audit", "Audit trail", "⌁"],
  ["/settings", "AI, API & OAuth", "⌘"],
];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [selectedProject, setSelectedProject] = useState("");

  useEffect(() => {
    setSelectedProject(window.localStorage.getItem("engram_project_id") || "00000000-0000-0000-0000-000000000001");
    document.cookie = `engram_project=${window.localStorage.getItem("engram_project_id") || "00000000-0000-0000-0000-000000000001"}; path=/; SameSite=Lax`;
    if (pathname !== "/login") {
      api<{ id: string; name: string }[]>("/api/v1/projects").then(setProjects).catch(() => {});
    }
  }, [pathname]);

  if (["/login", "/about", "/privacy", "/terms"].includes(pathname)) {
    return <>{children}</>;
  }

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
          <div className="brandMark">E</div>
          <div>
            <strong>Engram</strong>
            <span>private cognition layer</span>
          </div>
        </div>

        <label className="projectPicker">
          <span>Project</span>
          <select className="select" value={selectedProject} onChange={(event) => {
            window.localStorage.setItem("engram_project_id", event.target.value);
            document.cookie = `engram_project=${event.target.value}; path=/; SameSite=Lax`;
            window.location.reload();
          }}>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>

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
