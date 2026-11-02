// ── Personas — browser client ────────────────────────────────────────────────
// Thin wrappers over /api/personas (which proxies Python /personas/*). The
// runtime owns storage, sanitization, versions and the one-active rule. A
// persona is an append-only overlay: it never edits the built-in prompt.

export type PersonaStatus = 'draft' | 'active' | 'archived';

export interface PersonaSummary {
  id: string;
  name: string;
  description: string;
  status: PersonaStatus;
  isActive: boolean;
  hasDraft: boolean;
  activeVersion: number | null;
  instructionChars: number;
  createdAt: string;
  updatedAt: string;
}

export interface Persona extends PersonaSummary {
  instructions: string;
  draftInstructions: string | null;
  draftDiffers: boolean;
  contentHash: string;
}

export interface PersonaInput {
  name: string;
  description?: string;
  instructions: string;
}

export interface PersonaVersion {
  version: number;
  contentHash: string;
  createdAt: string;
  instructionChars: number;
}

export interface PersonaPreview {
  basePrompt: string;
  personaBlock: string;
  persona: Persona | null;
  isDefault: boolean;
  maxChars: number;
  effectiveChars: number;
}

export class PersonaApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'PersonaApiError';
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    cache: 'no-store',
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new PersonaApiError(
      typeof data.error === 'string' ? data.error : `Request failed (${res.status})`,
      res.status,
    );
  }
  return data as T;
}

export async function listPersonas(includeArchived = false): Promise<PersonaSummary[]> {
  const data = await request<{ personas?: PersonaSummary[] }>(
    `/api/personas${includeArchived ? '?includeArchived=true' : ''}`,
  );
  return data.personas ?? [];
}

export async function getPersona(id: string): Promise<Persona> {
  const data = await request<{ persona: Persona }>(`/api/personas/${encodeURIComponent(id)}`);
  return data.persona;
}

export async function createPersona(input: PersonaInput): Promise<Persona> {
  const data = await request<{ persona: Persona }>('/api/personas', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return data.persona;
}

export async function updatePersona(id: string, input: PersonaInput): Promise<Persona> {
  const data = await request<{ persona: Persona }>(`/api/personas/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
  return data.persona;
}

export async function activatePersona(id: string): Promise<Persona> {
  const data = await request<{ persona: Persona }>(
    `/api/personas/${encodeURIComponent(id)}/activate`,
    { method: 'POST' },
  );
  return data.persona;
}

export async function discardPersonaDraft(id: string): Promise<Persona> {
  const data = await request<{ persona: Persona }>(
    `/api/personas/${encodeURIComponent(id)}/discard`,
    { method: 'POST' },
  );
  return data.persona;
}

export async function restorePersonaVersion(id: string, version: number): Promise<Persona> {
  const data = await request<{ persona: Persona }>(
    `/api/personas/${encodeURIComponent(id)}/restore`,
    { method: 'POST', body: JSON.stringify({ version }) },
  );
  return data.persona;
}

export async function archivePersona(id: string): Promise<void> {
  await request(`/api/personas/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function resetDefaultPersona(): Promise<void> {
  await request('/api/personas/reset', { method: 'POST' });
}

export async function listPersonaVersions(id: string): Promise<PersonaVersion[]> {
  const data = await request<{ versions?: PersonaVersion[] }>(
    `/api/personas/${encodeURIComponent(id)}/versions`,
  );
  return data.versions ?? [];
}

export async function getPersonaPreview(): Promise<PersonaPreview> {
  return request<PersonaPreview>('/api/personas/preview');
}
