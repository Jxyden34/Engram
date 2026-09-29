export type Session = { origin: string; token: string; username: string; isAdmin: boolean; projectId: string; projectName?: string };
export type Project = { id: string; name: string; slug: string };
export type Memory = { id: string; title: string; content: string; memory_type: string; updated_at: string; tags?: string[] };
export type AgentDraft = { safe_to_merge: boolean; title?: string; content?: string; reason: string };
export type Proposal = { id: string; proposal_type: string; memory_id: string; memory_title?: string; related_memory_id?: string; related_title?: string; reason: string; evidence?: { draft?: AgentDraft; [key: string]: unknown }; draft_stale?: boolean };
export type ScanRun = { id: string; trigger_type: string; status: string; result?: { total: number }; error_message?: string; created_at: string };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export function normalizeOrigin(input: string): string {
  let url: URL;
  try { url = new URL(input.trim()); } catch { throw new Error('Enter a full server URL, such as https://engram.example.com'); }
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) {
    throw new Error('Use HTTPS for your Engram server (HTTP is allowed only for local development).');
  }
  if (url.username || url.password || url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) {
    throw new Error('Enter only the server origin, without a path or credentials.');
  }
  return url.origin;
}

async function response<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`);
  return body as T;
}

export async function login(origin: string, username: string, password: string) {
  return response<{ token: string; username: string; is_admin: boolean }>(await fetch(`${origin}/api/v1/mobile/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }),
  }));
}

export async function api<T>(session: Session, path: string, method = 'GET', body?: object): Promise<T> {
  return response<T>(await fetch(`${session.origin}${path}`, {
    method,
    headers: { Authorization: `Bearer ${session.token}`, 'X-Engram-Project': session.projectId, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  }));
}
