"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import LicencePage from "@/app/licence/page";
import { useBranding } from "./Branding";

import { navigationGroups, navigationGroup, isNavigationPage } from "@/lib/navigation";

const publicPaths = ["/login", "/about", "/privacy", "/terms", "/licence", "/join", "/setup"];
const commercialPaths = ["/dreams", "/licence", "/team", "/branding", "/handover", "/setup", "/reminders"];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const brand = useBranding();
  const router = useRouter();
  const activeGroup = navigationGroup(pathname) || navigationGroups[0];
  const subtabs = useRef<HTMLElement>(null);
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [version, setVersion] = useState("");
  const [edition, setEdition] = useState<any>(null);
  const [editionError, setEditionError] = useState("");
  const [due, setDue] = useState(0);

  useEffect(() => {
    if (!edition || edition.locked || publicPaths.includes(pathname)) return;
    const refresh = () => api<any[]>("/api/v1/reminders?due_only=true")
      .then(rows => setDue(rows.length)).catch(() => {});
    void refresh();
    const timer = window.setInterval(refresh, 60000);
    window.addEventListener("engram-reminders", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("engram-reminders", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [edition, pathname]);

  useEffect(() => {
    api("/api/v1/edition").then(setEdition).catch(e => setEditionError(e.message));
  }, []);

  useEffect(() => {
    const bar = subtabs.current;
    const selected = bar?.querySelector<HTMLElement>('[aria-current]');
    if (!bar || !selected) return;
    if (selected.offsetLeft < bar.scrollLeft) bar.scrollLeft = selected.offsetLeft;
    else if (selected.offsetLeft + selected.offsetWidth > bar.scrollLeft + bar.clientWidth)
      bar.scrollLeft = selected.offsetLeft + selected.offsetWidth - bar.clientWidth;
  }, [pathname]);

  useEffect(() => {
    setNavigationOpen(false);
    api<{version:string}>("/health").then(v => setVersion(v.version)).catch(() => setVersion(""));
    setSelectedProject(window.localStorage.getItem("engram_project_id") || "00000000-0000-0000-0000-000000000001");
    document.cookie = `engram_project=${window.localStorage.getItem("engram_project_id") || "00000000-0000-0000-0000-000000000001"}; path=/; SameSite=Lax`;
    if (edition && !edition.locked && !publicPaths.includes(pathname)) {
      api<{ id: string; name: string }[]>("/api/v1/projects").then(setProjects).catch(() => {});
    }
  }, [pathname, edition]);

  if (publicPaths.includes(pathname)) {
    return <>{children}</>;
  }
  if (!edition) return <main className="licencePage"><p role="status">{editionError || "Checking your workspace…"}</p>{editionError && <button onClick={() => window.location.reload()}>Try again</button>}</main>;
  if (edition.locked) return <LicencePage />;

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
          {brand.logo ? <img src={brand.logo} alt="" width={39} height={39}/> : <div className="brandMark" aria-hidden="true" />}
          <div>
            <strong>{brand.name}</strong>
            <span>{brand.tagline}</span>
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
          {navigationGroups.map(group => (
            <Link key={group.title} href={group.links[0][0]}
              aria-current={group === activeGroup ? "location" : undefined}
              className={`navLink primaryNavLink ${group === activeGroup ? "active" : ""}`}
              onClick={() => setNavigationOpen(false)}>
              <span className="navIcon" aria-hidden="true">{group.icon}</span>
              {group.title}
            </Link>
          ))}
        </nav>

        <div className="sidebarFoot">
          {edition.expires_at && new Date(edition.expires_at).getTime() - Date.now() < 30*86400000 &&
            <Link href="/licence" className="badge">Licence expires {new Date(edition.expires_at).toLocaleDateString()} · renew</Link>}
          <Link className="serverVersion" href="/system">Engram <span>{version ? `v${version}` : "Server information"}</span></Link>
          <button className="ghostButton" onClick={logout}>Sign out</button>
        </div>
      </aside>

      <main className="main" id="main-content" tabIndex={-1}>
        {due > 0 && <p className="successBox" role="status"><Link href="/reminders">{due} memory reminder{due === 1 ? " is" : "s are"} due →</Link></p>}
        <div className="sectionNavigation">
          <div className="sectionLabel">{activeGroup.title}</div>
          <nav className="sectionTabs" ref={subtabs} aria-label={`${activeGroup.title} pages`}>
            {activeGroup.links.filter(([href]) => edition.edition === "commercial" || !commercialPaths.includes(href)).map(([href,label]) => (
              <Link key={href} href={href}
                aria-current={isNavigationPage(pathname,href) ? (pathname === href ? "page" : "location") : undefined}
                className={`sectionTab ${isNavigationPage(pathname,href) ? "active" : ""}`}>
                {label}
              </Link>
            ))}
          </nav>
        </div>
        {children}
      </main>
    </div>
  );
}
