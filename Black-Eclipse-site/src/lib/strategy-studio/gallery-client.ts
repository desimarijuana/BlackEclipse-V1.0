// ── Gallery client (Strategy Studio) ────────────────────────────────────────
// Publishes a graded strategy into the LOCAL gallery. The gallery records the
// spec frozen at publication, the grade its evidence earned and the report it
// came from. This module only speaks to the front door; it stores nothing.

export interface PublishStrategyInput {
  strategyId: string;
  version?: string;
  name?: string;
  description?: string;
  author?: string;
  grade?: string;
  score?: number;
  summary?: string;
  report?: string;
  symbols?: string[];
}

export interface PublishedStrategy {
  id: string;
  name?: string;
  grade?: string | null;
  score?: number | null;
}

export interface PublishResult {
  status: string;
  summary: string;
  published?: PublishedStrategy;
}

export async function publishStrategy(input: PublishStrategyInput): Promise<PublishResult> {
  const response = await fetch('/api/harness/gallery', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  const payload = (await response.json().catch(() => ({}))) as {
    error?: string;
    detail?: { message?: string } | string;
    summary?: string;
    published?: PublishedStrategy;
    status?: string;
  };
  if (!response.ok) {
    const detail = payload.error ?? payload.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object' && 'message' in detail
          ? String(detail.message)
          : `the gallery returned ${response.status}`;
    throw new Error(message);
  }
  return {
    status: payload.status ?? 'OK',
    summary: payload.summary ?? 'Published.',
    published: payload.published,
  };
}
