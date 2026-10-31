/** Keep post-login navigation on this origin, including after URL normalization. */
export function internalReturnPath(value: string | null, origin: string): string {
  if (!value?.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(value)) return "/";
  try {
    const base = new URL(origin);
    const destination = new URL(value, base);
    if (destination.origin !== base.origin || destination.pathname.startsWith("//")) return "/";
    return destination.pathname + destination.search + destination.hash;
  } catch {
    return "/";
  }
}
