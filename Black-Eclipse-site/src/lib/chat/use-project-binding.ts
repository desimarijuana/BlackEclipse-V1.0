'use client';

// ── The chat's bound project folder (client) ─────────────────────────────────
// A tiny read of `/api/chat/session/project`, shared by the composer's `@`
// search and anything else that needs the approved root without re-implementing
// the fetch. It returns IDs and labels only; the runtime still resolves the id.

import { useEffect, useState } from 'react';

export interface ProjectBinding {
  rootId: string | null;
  path: string | null;
  label: string;
  runtime: 'ready' | 'unavailable' | 'error';
}

function labelFromPath(path: string | null | undefined): string {
  if (!path) return 'Eclipse repo';
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export function useProjectBinding(chatId: string | null | undefined): ProjectBinding {
  const [state, setState] = useState<ProjectBinding>({
    rootId: null,
    path: null,
    label: 'Eclipse repo',
    runtime: 'ready',
  });

  useEffect(() => {
    if (!chatId) {
      setState({ rootId: null, path: null, label: 'Eclipse repo', runtime: 'ready' });
      return;
    }
    let alive = true;
    void (async () => {
      try {
        const res = await fetch(`/api/chat/session/project?chatId=${encodeURIComponent(chatId)}`, {
          cache: 'no-store',
        });
        const data = (await res.json().catch(() => ({}))) as {
          project?: { workspaceRootId: string | null; workspacePath: string | null } | null;
          roots?: Array<{ id: string; path: string; label?: string | null }>;
          runtime?: 'ready' | 'unavailable' | 'error';
        };
        if (!alive) return;
        const rootId = data.project?.workspaceRootId ?? null;
        const root = rootId ? data.roots?.find((item) => item.id === rootId) : null;
        setState({
          rootId,
          path: data.project?.workspacePath ?? root?.path ?? null,
          label: root?.label?.trim() || labelFromPath(data.project?.workspacePath ?? root?.path),
          runtime: data.runtime ?? 'ready',
        });
      } catch {
        if (alive) setState((prev) => ({ ...prev, runtime: 'error' }));
      }
    })();
    return () => { alive = false; };
  }, [chatId]);

  return state;
}
