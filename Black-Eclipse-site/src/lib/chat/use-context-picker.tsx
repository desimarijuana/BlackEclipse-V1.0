'use client';

// ── Composer context picker (shared wiring) ──────────────────────────────────
// Keeps the chat surface small: the composer only calls `open()` / `openImages()`
// and renders `host` once. The host owns the unified FileSourcePicker, the
// upload path (with provenance), and the cross-surface "attach this project
// file" event the editor emits.

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { FileSourcePicker } from '@/components/workspace/file-source-picker';
import type { SessionController } from './use-session';
import {
  ATTACH_PROJECT_FILE_EVENT,
  leafOf,
  type AttachProjectFileDetail,
} from './file-sources';

export { ATTACH_PROJECT_FILE_EVENT };
export type { AttachProjectFileDetail };

export interface ContextPickerController {
  open: () => void;
  openImages: () => void;
  host: ReactNode;
}

export function useContextPicker({
  controller,
  chatId,
}: {
  controller: SessionController;
  chatId: string | null;
}): ContextPickerController {
  const [mode, setMode] = useState<'all' | 'images' | null>(null);

  // The editor (or any other surface) can ask the ACTIVE chat to attach a
  // project file without owning the session controller itself.
  useEffect(() => {
    const onAttach = (event: Event) => {
      const detail = (event as CustomEvent<AttachProjectFileDetail>).detail;
      if (!detail?.path) return;
      void controller.attachProjectFile({
        name: leafOf(detail.path),
        path: detail.path,
        rootId: detail.rootId ?? null,
        rootLabel: detail.rootLabel ?? null,
      });
    };
    window.addEventListener(ATTACH_PROJECT_FILE_EVENT, onAttach);
    return () => window.removeEventListener(ATTACH_PROJECT_FILE_EVENT, onAttach);
  }, [controller]);

  const open = useCallback(() => setMode('all'), []);
  const openImages = useCallback(() => setMode('images'), []);

  const host = mode ? (
    <FileSourcePicker
      mode={mode}
      chatId={chatId}
      onClose={() => setMode(null)}
      onPick={(files) => { void controller.uploadFiles(files); }}
    />
  ) : null;

  return { open, openImages, host };
}
