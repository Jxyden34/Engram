"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";

const groups = [
  { title: "Library", links: [
  ["/", "Overview", "◈"],
  ["/memories", "Memories", "◎"],
  ["/documents", "Documents", "▱"],
  ["/knowledge", "Knowledge graph", "◎"],
  ["/timeline", "Timeline", "◷"],
  ] },
  { title: "Workspace", links: [
  ["/intelligence", "Intelligence", "✧"],
  ["/projects", "Projects", "▦"],
  ["/agent", "Memory Agent", "✧"],
  ] },
  { title: "Capture & review", links: [
  ["/imports", "Memory Inbox", "✦"],
  ["/connectors", "Connectors", "⇄"],
  ["/approvals", "Approvals", "◇"],
  ] },
  { title: "System", links: [
  ["/system", "Health & about", "♡"],
  ["/observability", "Observability", "◴"],
  ["/disaster-recovery", "Disaster Recovery", "⛨"],
  ["/audit", "Audit trail", "⌁"],
  ["/settings", "AI, API & OAuth", "⌘"],
  ] },
];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [version, setVersion] = useState("");

  useEffect(() => {
    setNavigationOpen(false);
    api<{version:string}>("/health").then(v => setVersion(v.version)).catch(() => setVersion(""));
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
      <a className="skipLink" href="#main-content">Skip to content</a>
      <aside className={`sidebar ${navigationOpen ? "navigationOpen" : ""}`}>
        <div className="brand">
          <div className="brandMark" aria-hidden="true" />
          <div>
            <strong>Engram</strong>
            <span>private cognition layer</span>
          </div>
        </div>
        <button type="button" className="ghostButton navigationToggle" aria-expanded={navigationOpen} aria-controls="sidebar-navigation" onClick={() => setNavigationOpen(!navigationOpen)}>{navigationOpen ? "Close navigation" : "Navigation"}</button>

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

        <nav id="sidebar-navigation" className="sidebarNavigation" aria-label="Main navigation">
          {groups.map(group => <div className="navGroup" key={group.title}>
          <div className="navGroupTitle">{group.title}</div>
          {group.links.map(([href, label, icon]) => (
            <Link
              key={href}
              href={href}
              aria-current={pathname === href || (href !== "/" && pathname.startsWith(href)) ? "page" : undefined}
              className={
                pathname === href || (href !== "/" && pathname.startsWith(href))
                  ? "navLink active"
                  : "navLink"
              }
            >
              <span className="navIcon" aria-hidden="true">{icon}</span>
              {label}
            </Link>
          ))}</div>)}
        </nav>

        <div className="sidebarFoot">
          <Link className="serverVersion" href="/system">Engram <span>{version ? `v${version}` : "Server information"}</span></Link>
          <button className="ghostButton" onClick={logout}>Sign out</button>
        </div>
      </aside>

      <main className="main" id="main-content" tabIndex={-1}>{children}</main>
    </div>
  );
}
