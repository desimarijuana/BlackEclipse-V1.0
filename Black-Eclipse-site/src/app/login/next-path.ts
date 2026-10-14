// The login page honors a `?next=` return path supplied by the middleware
// redirect. Only a SAME-ORIGIN absolute path may pass: an absolute or
// protocol-relative URL would turn the sign-in page into an open redirect, and
// `next=/login` would loop. Pure and total — anything else falls back to "/".
export function safeNext(raw: string | null | undefined): string {
  const value = (raw ?? "").trim();
  if (!value.startsWith("/") || value.startsWith("//")) return "/";
  if (value.includes("\\")) return "/";
  if (value === "/login" || value.startsWith("/login?") || value.startsWith("/login/")) return "/";
  return value;
}
