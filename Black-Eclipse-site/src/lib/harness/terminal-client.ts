// ─── Terminal subsystem front door ──────────────────────────────────────────
// A thin, typed proxy over the Python runtime's /terminal routes. Like
// code-client.ts it adds NO execution logic: it validates nothing the runtime
// owns, forwards with the operator token, and returns what the runtime reports.
// The terminal backend is shared by the agent tools and this UI, so there is one
// source of truth for process/session state.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export interface TerminalCapabilities {
  platform: string;
  architecture: string;
  defaultShell: string | null;
  availableShells: string[];
  wsl: { available: boolean; distributions: string[]; default: string | null; reason?: string | null };
  runtimes: string[];
  pty: boolean;
  processManagement: boolean;
  portDetection: boolean;
  docker: boolean;
  ssh: boolean;
}

export interface CommandResult {
  executionId: string;
  status: string;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  truncated: boolean;
  cwd: string;
  runtime: string;
  command: string;
  stdoutSequence: number;
  stderrSequence: number;
  error?: { type: string; category: string; message: string };
}

export interface TerminalSessionInfo {
  sessionId: string;
  runtime: string;
  shell: string;
  pid: number | null;
  cwd: string;
  status: string;
  rows: number;
  columns: number;
  envKeys: string[];
  workspaceId: string | null;
  agentId: string | null;
  pty: boolean;
}

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
  error?: { category: string; message: string } | null;
}

export interface OutputWindow {
  chunks: Array<{ sequence: number; stream: string; timestamp: string; data: string }>;
  text: string;
  count: number;
  totalLines: number;
  nextSequence: number;
  droppedLines: number;
  status?: string;
}

export interface PortEntry {
  port: number;
  pid: number | null;
  processId: string | null;
  address: string | null;
  protocol: string;
  status: string;
}

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const { timeoutMs = 120_000, ...rest } = init;
  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(rest.headers ?? {}),
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

// ── Capabilities / ports / system ───────────────────────────────────────────

export async function getTerminalCapabilities(): Promise<TerminalCapabilities> {
  const body = await request<{ capabilities: TerminalCapabilities }>("/terminal/capabilities", { method: "GET" });
  return body.capabilities;
}

export async function listPorts(): Promise<{ ports: PortEntry[]; summary: unknown }> {
  const body = await request<{ ports: PortEntry[]; summary: unknown }>("/terminal/ports", { method: "GET" });
  return { ports: body.ports ?? [], summary: body.summary };
}

export async function findPortOwner(port: number): Promise<PortEntry | null> {
  const body = await request<{ owner: PortEntry | null }>(`/terminal/ports?port=${encodeURIComponent(port)}`, {
    method: "GET",
  });
  return body.owner ?? null;
}

export async function getTerminalSystem(): Promise<Record<string, unknown>> {
  return request("/terminal/system", { method: "GET" });
}

// ── Foreground execution ────────────────────────────────────────────────────

export async function executeTerminalCommand(
  command: string,
  opts: { cwd?: string; shell?: string; runtime?: string; timeoutMs?: number } = {},
): Promise<CommandResult> {
  const body = await request<{ result: CommandResult }>("/terminal/execute", {
    method: "POST",
    body: JSON.stringify({
      command,
      cwd: opts.cwd,
      shell: opts.shell,
      runtime: opts.runtime ?? "local",
      timeoutMs: opts.timeoutMs,
    }),
    timeoutMs: (opts.timeoutMs ?? 120_000) + 5_000,
  });
  return body.result;
}

// ── Sessions ────────────────────────────────────────────────────────────────

export async function listTerminalSessions(): Promise<TerminalSessionInfo[]> {
  const body = await request<{ sessions: TerminalSessionInfo[] }>("/terminal/sessions", { method: "GET" });
  return body.sessions ?? [];
}

export async function openTerminalSession(
  opts: { shell?: string; runtime?: string; cwd?: string; rows?: number; columns?: number } = {},
): Promise<TerminalSessionInfo> {
  const body = await request<{ session: TerminalSessionInfo }>("/terminal/sessions", {
    method: "POST",
    body: JSON.stringify(opts),
  });
  return body.session;
}

export async function closeTerminalSession(sessionId: string): Promise<void> {
  await request(`/terminal/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

export async function runInTerminalSession(
  sessionId: string,
  command: string,
  timeoutMs?: number,
): Promise<{ text: string; timedOut: boolean; cwd?: string }> {
  const body = await request<{ result: { text: string; timedOut: boolean; data?: { cwd?: string } } }>(
    `/terminal/sessions/${encodeURIComponent(sessionId)}/run`,
    { method: "POST", body: JSON.stringify({ command, timeoutMs }), timeoutMs: (timeoutMs ?? 120_000) + 5_000 },
  );
  return { text: body.result.text, timedOut: body.result.timedOut, cwd: body.result.data?.cwd };
}

export async function writeTerminalSessionInput(sessionId: string, input: string, newline = true): Promise<void> {
  await request(`/terminal/sessions/${encodeURIComponent(sessionId)}/input`, {
    method: "POST",
    body: JSON.stringify({ input, newline }),
  });
}

export async function readTerminalSessionOutput(
  sessionId: string,
  opts: { cursor?: number; tail?: number } = {},
): Promise<OutputWindow> {
  const params = new URLSearchParams();
  if (opts.cursor != null) params.set("cursor", String(opts.cursor));
  if (opts.tail != null) params.set("tail", String(opts.tail));
  const body = await request<{ output: OutputWindow }>(
    `/terminal/sessions/${encodeURIComponent(sessionId)}/output?${params.toString()}`,
    { method: "GET" },
  );
  return body.output;
}

export async function sendTerminalSessionControl(sessionId: string, key: "c" | "d" | "z"): Promise<void> {
  await request(`/terminal/sessions/${encodeURIComponent(sessionId)}/control`, {
    method: "POST",
    body: JSON.stringify({ signal: key }),
  });
}

export async function resizeTerminalSession(sessionId: string, rows: number, columns: number): Promise<void> {
  await request(`/terminal/sessions/${encodeURIComponent(sessionId)}/resize`, {
    method: "POST",
    body: JSON.stringify({ rows, columns }),
  });
}

// ── Processes ───────────────────────────────────────────────────────────────

export async function listTerminalProcesses(): Promise<ProcessInfo[]> {
  const body = await request<{ processes: ProcessInfo[] }>("/terminal/processes", { method: "GET" });
  return body.processes ?? [];
}

export async function stopTerminalProcess(processId: string): Promise<void> {
  await request(`/terminal/processes/${encodeURIComponent(processId)}/stop`, { method: "POST" });
}

export async function killTerminalProcess(processId: string): Promise<void> {
  await request(`/terminal/processes/${encodeURIComponent(processId)}/kill`, { method: "POST" });
}

export async function restartTerminalProcess(processId: string): Promise<ProcessInfo> {
  const body = await request<{ process: ProcessInfo }>(
    `/terminal/processes/${encodeURIComponent(processId)}/restart`,
    { method: "POST" },
  );
  return body.process;
}

export async function readTerminalProcessOutput(
  processId: string,
  opts: { cursor?: number; tail?: number } = {},
): Promise<OutputWindow> {
  const params = new URLSearchParams();
  if (opts.cursor != null) params.set("cursor", String(opts.cursor));
  if (opts.tail != null) params.set("tail", String(opts.tail));
  const body = await request<{ output: OutputWindow }>(
    `/terminal/processes/${encodeURIComponent(processId)}/output?${params.toString()}`,
    { method: "GET" },
  );
  return body.output;
}
