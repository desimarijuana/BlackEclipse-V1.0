// ─── Terminal browser client ─────────────────────────────────────────────────
// The UI talks to the Next.js proxy (`/api/terminal/**`), which forwards to the
// Python runtime. This module MUST stay client-safe: fetch only, no prisma, no
// child_process, no fs, no runtime secret. The server owns execution state.

export interface ProcessInfo {
  processId: string;
  pid: number | null;
  command: string;
  cwd: string;
  runtime: string;
  shell: string;
  state: string;
  exitCode: number | null;
  ports: number[];
  agentId: string | null;
  purpose: string | null;
}

export interface PortEntry {
  port: number;
  pid: number | null;
  processId: string | null;
  address: string | null;
  protocol: string;
  status: string;
}

export interface OutputWindow {
  text: string;
  count: number;
  totalLines: number;
  nextSequence: number;
  droppedLines: number;
  status?: string;
}

export interface TerminalSessionInfo {
  sessionId: string;
  shell: string;
  cwd: string;
  status: string;
  pid: number | null;
  pty: boolean;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new Error(body.error ?? `request failed (${res.status})`);
  return body;
}

export function listTerminalProcesses(): Promise<ProcessInfo[]> {
  return api<{ processes: ProcessInfo[] }>("/api/terminal/processes").then((b) => b.processes ?? []);
}

export function stopTerminalProcess(processId: string): Promise<unknown> {
  return api(`/api/terminal/processes/${encodeURIComponent(processId)}/stop`, { method: "POST" });
}

export function killTerminalProcess(processId: string): Promise<unknown> {
  return api(`/api/terminal/processes/${encodeURIComponent(processId)}/kill`, { method: "POST" });
}

export function restartTerminalProcess(processId: string): Promise<unknown> {
  return api(`/api/terminal/processes/${encodeURIComponent(processId)}/restart`, { method: "POST" });
}

export function readTerminalProcessOutput(
  processId: string,
  opts: { cursor?: number; tail?: number } = {},
): Promise<OutputWindow> {
  const params = new URLSearchParams();
  if (opts.cursor != null) params.set("cursor", String(opts.cursor));
  if (opts.tail != null) params.set("tail", String(opts.tail));
  return api<{ output: OutputWindow }>(
    `/api/terminal/processes/${encodeURIComponent(processId)}/output?${params.toString()}`,
  ).then((b) => b.output);
}

export function listPorts(): Promise<{ ports: PortEntry[] }> {
  return api<{ ports: PortEntry[] }>("/api/terminal/ports").then((b) => ({ ports: b.ports ?? [] }));
}

export function listTerminalSessions(): Promise<TerminalSessionInfo[]> {
  return api<{ sessions: TerminalSessionInfo[] }>("/api/terminal/sessions").then((b) => b.sessions ?? []);
}

export function getTerminalResources(): Promise<Record<string, unknown>> {
  return api("/api/terminal/resources");
}

export function openTerminalSession(
  opts: {
    shell?: string;
    runtime?: string;
    cwd?: string;
    rows?: number;
    columns?: number;
    /** A durable terminal id: reopening reattaches to the same shell. */
    owner?: string;
  } = {},
): Promise<TerminalSessionInfo> {
  return api<{ session: TerminalSessionInfo }>("/api/terminal/sessions", {
    method: "POST",
    body: JSON.stringify(opts),
  }).then((b) => b.session);
}

export function closeTerminalSession(sessionId: string): Promise<unknown> {
  return api(`/api/terminal/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

export function resizeTerminalSession(sessionId: string, rows: number, columns: number): Promise<unknown> {
  return api(`/api/terminal/sessions/${encodeURIComponent(sessionId)}/resize`, {
    method: "POST",
    body: JSON.stringify({ rows, columns }),
  });
}

export function runInTerminalSession(
  sessionId: string,
  command: string,
  timeoutMs?: number,
): Promise<{ text: string; timedOut: boolean; cwd?: string }> {
  return api<{ result: { text: string; timedOut: boolean; data?: { cwd?: string } } }>(
    `/api/terminal/sessions/${encodeURIComponent(sessionId)}/run`,
    { method: "POST", body: JSON.stringify({ command, timeoutMs }) },
  ).then((b) => ({ text: b.result.text, timedOut: b.result.timedOut, cwd: b.result.data?.cwd }));
}

export function writeTerminalSessionInput(sessionId: string, input: string, newline = true): Promise<unknown> {
  return api(`/api/terminal/sessions/${encodeURIComponent(sessionId)}/input`, {
    method: "POST",
    body: JSON.stringify({ input, newline }),
  });
}

export function sendTerminalSessionControl(sessionId: string, key: "c" | "d" | "z"): Promise<unknown> {
  return api(`/api/terminal/sessions/${encodeURIComponent(sessionId)}/control`, {
    method: "POST",
    body: JSON.stringify({ signal: key }),
  });
}

export interface RawStream {
  text: string;
  nextSequence: number;
  running: boolean;
  cwd: string;
  droppedLines: number;
}

export function sendTerminalRaw(sessionId: string, data: string): Promise<unknown> {
  return api(`/api/terminal/sessions/${encodeURIComponent(sessionId)}/raw`, {
    method: "POST",
    body: JSON.stringify({ data }),
  });
}

export function streamTerminalOutput(
  sessionId: string,
  since: number,
  timeout = 15,
  signal?: AbortSignal,
): Promise<RawStream> {
  const params = new URLSearchParams({ since: String(since), timeout: String(timeout) });
  return api<RawStream & { text: string }>(
    `/api/terminal/sessions/${encodeURIComponent(sessionId)}/stream?${params.toString()}`,
    { signal },
  ).then((b) => ({
    text: b.text ?? "",
    nextSequence: b.nextSequence ?? since,
    running: b.running ?? false,
    cwd: b.cwd ?? "",
    droppedLines: b.droppedLines ?? 0,
  }));
}

export function executeTerminalCommand(
  command: string,
  opts: { cwd?: string; runtime?: string; timeoutMs?: number } = {},
): Promise<{
  status: string;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  error?: { category: string; message: string };
}> {
  return api<{ result: never }>("/api/terminal/execute", {
    method: "POST",
    body: JSON.stringify({ command, ...opts }),
  }).then((b) => b.result);
}
