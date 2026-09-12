export function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const item = document.cookie
    .split("; ")
    .find((row) => row.startsWith("memory_csrf="));
  return item ? decodeURIComponent(item.split("=")[1]) : "";
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  const method = (init.method || "GET").toUpperCase();

  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  if (response.status === 401 && typeof window !== "undefined" && !path.includes("/auth/login")) {
    window.location.href = "/login";
    throw new Error("Authentication required");
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload?.detail
        ? typeof payload.detail === "string"
          ? payload.detail
          : JSON.stringify(payload.detail)
        : String(payload);
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return payload as T;
}

export function dateText(value?: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}
