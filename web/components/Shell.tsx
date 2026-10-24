"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";
import LicencePage from "@/app/licence/page";
import {useBranding} from './Branding';

const links = [
  ["/", "Overview", "◈"],
  ["/memories", "Memories", "◎"],
  ["/intelligence", "Intelligence", "✧"],
  ["/documents", "Documents", "▱"],
  ["/projects", "Projects", "▦"],
  ["/agent", "Memory Agent", "✧"],
  ["/dreams", "Dream Lab", "☾"],
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
  ["/team", "Team workspace", "♧"],
  ["/branding", "Company branding", "◈"],
  ["/handover", "Project handover", "↗"],
  ["/setup", "Setup wizard", "◇"],
  ["/reminders", "Reminders", "◷"],
];
const publicPaths = ["/login", "/about", "/privacy", "/terms", "/licence", "/join", "/setup"];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const brand=useBranding();
  const router = useRouter();
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [edition, setEdition] = useState<any>(null);
  const [editionError, setEditionError] = useState("");
  const [due,setDue]=useState(0);
  useEffect(()=>{
    if(!edition||edition.locked||publicPaths.includes(pathname))return;
    const refresh=()=>api<any[]>('/api/v1/reminders?due_only=true').then(rows=>setDue(rows.length)).catch(()=>{});
    void refresh();const timer=window.setInterval(refresh,60000);window.addEventListener('engram-reminders',refresh);window.addEventListener('focus',refresh);
    return()=>{clearInterval(timer);window.removeEventListener('engram-reminders',refresh);window.removeEventListener('focus',refresh)};
  },[edition,pathname]);
  useEffect(() => { api("/api/v1/edition").then(setEdition).catch(e => setEditionError(e.message)); }, []);

  useEffect(() => {
    setSelectedProject(window.localStorage.getItem("engram_project_id") || "00000000-0000-0000-0000-000000000001");
    document.cookie = `engram_project=${window.localStorage.getItem("engram_project_id") || "00000000-0000-0000-0000-000000000001"}; path=/; SameSite=Lax`;
    if (edition && !edition.locked && !publicPaths.includes(pathname)) {
      api<{ id: string; name: string }[]>("/api/v1/projects").then(items=>{
        setProjects(items);
        const current=window.localStorage.getItem('engram_project_id')||'00000000-0000-0000-0000-000000000001';
        if(items.length&&!items.some(item=>item.id===current)){
          window.localStorage.setItem('engram_project_id',items[0].id);
          document.cookie=`engram_project=${items[0].id}; path=/; SameSite=Lax`;
          window.location.reload();
        }
      }).catch(() => {});
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
          {brand.logo?<img src={brand.logo} alt="" width={39} height={39}/>:<div className="brandMark" aria-hidden="true" />}
          <div>
            <strong>{brand.name}</strong>
            <span>{brand.tagline}</span>
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
          {links.filter(([href])=>edition.edition==='commercial'||!['/team','/branding','/handover','/setup'].includes(href)).map(([href, label, icon]) => (
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
          {edition.expires_at&&new Date(edition.expires_at).getTime()-Date.now()<30*86400000&&<Link href="/licence" className="badge">Licence expires {new Date(edition.expires_at).toLocaleDateString()} · renew</Link>}
          <div className="secureDot"><i /> Encrypted edge</div>
          <button className="ghostButton" onClick={logout}>Sign out</button>
        </div>
      </aside>

      <main className="main">{due>0&&<p className="successBox" role="status"><Link href="/reminders">{due} memory reminder{due===1?' is':'s are'} due →</Link></p>}{children}</main>
    </div>
  );
}
