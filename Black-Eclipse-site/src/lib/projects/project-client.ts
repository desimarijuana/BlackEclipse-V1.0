// ── Projects client + the active project ─────────────────────────────────────
// A project is the named scope a chat turn can be pinned to. The runtime owns
// the store; this module is the browser's thin door onto it, plus the one
// piece of local state that makes it usable: WHICH project the chat is
// currently in.
//
// The active id is a LOCAL preference, not a grant: it only says which project
// the next turn should be scoped to. The runtime resolves it, and a project
// that does not exist is reported rather than ignored.

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  symbols: string[];
  tags: string[];
  status: string;
  createdAt: string;
  updatedAt: string;
  lastActivityAt: string;
  archivedAt?: string | null;
}

export interface ProjectMember {
  id: string;
  projectId: string;
  kind: string;
  ref: string;
  label: string;
  meta: Record<string, unknown>;
  createdAt: string;
}

export interface ProjectDetail {
  project: ProjectSummary;
  members: ProjectMember[];
  membersByKind: Record<string, ProjectMember[]>;
  memberCount: number;
}

const BASE = "/api/harness/projects";

/** The localStorage key holding the project the chat is currently in. */
const ACTIVE_KEY = "be_active_project";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const payload = (await res.json().catch(() => ({}))) as {
    error?: unknown;
    detail?: unknown;
  };
  if (!res.ok) {
    const detail = payload.error ?? payload.detail;
    const message = typeof detail === "string" ? detail : `request failed (${res.status})`;
    throw new Error(message);
  }
  return payload as T;
}

export interface CuratedMember {
  id: string;
  kind: string;
  ref: string;
  label: string;
  score: number;
  reason: string;
  createdAt: string;
  meta: Record<string, unknown>;
}

export interface ProjectDigest {
  projectId: string;
  name: string;
  headline: string;
  summary: string;
  members: CuratedMember[];
  memberCount: number;
  gaps: string[];
  counts: Record<string, number>;
}

export interface ProjectProposal {
  id: string;
  title: string;
  rationale: string;
  evidence: string[];
  action: { tool?: string; args?: Record<string, unknown> };
  priority: number;
}

export interface ProjectProposals {
  available: boolean;
  projectId: string;
  summary: string;
  proposals: ProjectProposal[];
  proposalCount: number;
}

export const projectClient = {
  list: (status?: string) => {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return jsonFetch<{ projects: ProjectSummary[]; count: number }>(query).then(
      (r) => r.projects ?? [],
    );
  },

  create: (body: {
    name: string;
    description?: string;
    symbols?: string[];
    tags?: string[];
  }) => jsonFetch<{ project: ProjectSummary }>("/", { method: "POST", body: JSON.stringify(body) })
    .then((r) => r.project),

  get: (id: string) =>
    jsonFetch<ProjectDetail>(`/${encodeURIComponent(id)}`),

  digest: (id: string) =>
    jsonFetch<{ digest: ProjectDigest }>(`/${encodeURIComponent(id)}/digest`)
      .then((r) => r.digest),

  proposals: (id: string) =>
    jsonFetch<ProjectProposals>(`/${encodeURIComponent(id)}/proposals`),

  runProposal: (id: string, proposalId: string) =>
    jsonFetch<{ run: { status: string; summary: string; experimentId?: string | null } }>(
      `/${encodeURIComponent(id)}/proposals/${encodeURIComponent(proposalId)}/run`,
      { method: "POST" },
    ),

  /** Attach a strategy/experiment/artifact/note to a project. */
  addMember: (
    id: string,
    body: { kind: string; ref: string; label?: string; meta?: Record<string, unknown> },
  ) =>
    jsonFetch<{ member: ProjectMember }>(`/${encodeURIComponent(id)}/members`, {
      method: "POST",
      body: JSON.stringify(body),
    }).then((r) => r.member),
};

/**
 * The project the chat is currently scoped to, or null.
 *
 * The value is a preference, not a permission: it only decides which project
 * the next turn names. A stale or unknown id is harmless — the runtime reports
 * it — so this never throws and never blocks the chat.
 */
export function getActiveProjectId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(ACTIVE_KEY);
    return value && /^[A-Za-z0-9_-]{1,64}$/.test(value) ? value : null;
  } catch {
    return null;
  }
}

/** Pin the chat to a project. Pass null to clear it. */
export function setActiveProjectId(id: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (!id) {
      window.localStorage.removeItem(ACTIVE_KEY);
      return;
    }
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) return;
    window.localStorage.setItem(ACTIVE_KEY, id);
  } catch {
    // A blocked localStorage must never break the chat.
  }
}
