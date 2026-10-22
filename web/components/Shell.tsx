"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";
import LicencePage from "@/app/licence/page";

const links = [
  ["/", "Overview", "◈"],
  ["/memories", "Memories", "◎"],
  ["/intelligence", "Intelligence", "✧"],
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
  ["/licence", "Licence", "◇"],
];
const publicPaths = ["/login", "/about", "/privacy", "/terms", "/licence"];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [edition, setEdition] = useState<any>(null);
  const [editionError, setEditionError] = useState("");
  useEffect(() => { api("/api/v1/edition").then(setEdition).catch(e => setEditionError(e.message)); }, []);

  useEffect(() => {
    setSelectedProject(window.localStorage.getItem("engram_project_id") || "00000000-0000-0000-0000-000000000001");
    document.cookie = `engram_project=${window.localStorage.getItem("engram_project_id") || "00000000-0000-0000-0000-000000000001"}; path=/; SameSite=Lax`;
    if (edition && !edition.locked && !publicPaths.includes(pathname)) {
      api<{ id: string; name: string }[]>("/api/v1/projects").then(setProjects).catch(() => {});
    }
  }, [pathname, edition]);

  if (publicPaths.includes(pathname)) {
    return <>{children}</>;
  }
  if (!edition) return <main className="licencePage"><p role="status">{editionError || "Checking your workspace…"}</p>{editionError && <button onClick={()=>window.location.reload()}>Try again</button>}</main>;
  if (edition.locked) return <LicencePage/>;

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
          <div className="brandMark" aria-hidden="true" />
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
