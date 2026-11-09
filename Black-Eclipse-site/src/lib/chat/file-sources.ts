// ── File sources (pure) ──────────────────────────────────────────────────────
// Shared vocabulary for the file picker, the composer chips and `@` search.
// Dependency-free (type-only imports) so it is unit-testable and safe in both
// server and client bundles.
//
// The one idea: a file is never just a name. It always carries WHERE it is from
// — a workspace folder (relative path + root label), this computer (a local
// upload), or a paste. The UI can then say "src/components/chat · Project"
// instead of an anonymous `chat-input.tsx`.

import type { FileProvenance, FileOrigin } from './session-types';

export type { FileOrigin, FileProvenance };

/** A file the user picked, ready to upload with its provenance attached. */
export interface PickedFile {
  file: File;
  meta: FileProvenance;
}

/** One searchable project file returned to the composer's `@` palette. */
export interface FileRef {
  /** Leaf file name. */
  name: string;
  /** Workspace-relative path, e.g. `src/components/chat/chat-input.tsx`. */
  path: string;
  rootId?: string | null;
  rootLabel?: string | null;
  /** Size in bytes when the runtime reported it. */
  bytes?: number | null;
}

/**
 * The window event another surface (the editor) dispatches to attach one
 * project file to the ACTIVE chat. Kept in this pure module so the editor does
 * not have to import the composer's picker component.
 */
export const ATTACH_PROJECT_FILE_EVENT = 'eclipse:attach-project-file';

export interface AttachProjectFileDetail {
  path: string;
  rootId?: string | null;
  rootLabel?: string | null;
}

/** The folder part of a relative path (`src/components/chat`), or '' at root. */
export function folderOf(relativePath: string | null | undefined): string {
  const normalized = (relativePath ?? '').replace(/\\/g, '/');
  const cut = normalized.lastIndexOf('/');
  return cut === -1 ? '' : normalized.slice(0, cut);
}

/** The last path segment (a file or folder name). */
export function leafOf(relativePath: string | null | undefined): string {
  const normalized = (relativePath ?? '').replace(/\\/g, '/').replace(/\/+$/, '');
  const cut = normalized.lastIndexOf('/');
  return cut === -1 ? normalized : normalized.slice(cut + 1);
}

/** Human label for an origin badge. */
export function originLabel(origin: FileOrigin | null | undefined): string {
  switch (origin) {
    case 'project':
      return 'Project';
    case 'paste':
      return 'Pasted';
    case 'upload':
    default:
      return 'Local';
  }
}

/** A one-line "where is this from" description, used as a chip subtitle. */
export function describeSource(meta: FileProvenance | null | undefined): string {
  if (!meta) return 'This computer';
  if (meta.origin === 'project') {
    const folder = folderOf(meta.sourcePath);
    const root = meta.rootLabel?.trim() || 'Project';
    return folder ? `${root} › ${folder}` : root;
  }
  if (meta.origin === 'paste') return 'Pasted text';
  return 'Local · uploaded copy';
}

/** Format bytes the same way the session bar does, without inventing precision. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isSubsequence(needle: string, haystack: string): boolean {
  let i = 0;
  for (const ch of haystack) {
    if (ch === needle[i]) i += 1;
    if (i === needle.length) return true;
  }
  return needle.length === 0;
}

/**
 * Score a project file against a query. The leaf name dominates; the folder
 * path is a fallback so `src/components` still surfaces its files. Higher is
 * better, 0 means no match. Deterministic so results do not jump between keys.
 */
export function scoreFile(file: FileRef, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 1;
  const name = file.name.toLowerCase();
  const path = file.path.toLowerCase();
  if (name === q) return 1000;
  if (name.startsWith(q)) return 800 - name.length;
  if (name.includes(q)) return 600 - name.length;
  if (path.endsWith(`/${q}`)) return 500 - path.length;
  if (path.startsWith(q)) return 400 - path.length;
  if (path.includes(q)) return 300 - path.length;
  if (isSubsequence(q, name)) return 200;
  if (isSubsequence(q, path)) return 100;
  return 0;
}

/** Search a project file list. Stable ordering, leaf matches first. */
export function searchFiles(files: readonly FileRef[], query: string, limit = 8): FileRef[] {
  const q = (query ?? '').trim();
  if (!files.length) return [];
  if (!q) {
    return [...files].sort((a, b) => a.path.localeCompare(b.path)).slice(0, limit);
  }
  return files
    .map((file) => ({ file, score: scoreFile(file, q) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.file.path.localeCompare(b.file.path))
    .map((entry) => entry.file)
    .slice(0, limit);
}

/** A flat path's breadcrumb pieces: `a/b/c` → ['a','b','c']. */
export function breadcrumbs(relativeDir: string | null | undefined): string[] {
  return (relativeDir ?? '.')
    .replace(/\\/g, '/')
    .split('/')
    .filter((part) => part && part !== '.');
}

/** The parent of a relative directory ('' when already at the root). */
export function parentDir(relativeDir: string | null | undefined): string {
  const parts = breadcrumbs(relativeDir);
  parts.pop();
  return parts.join('/');
}

/** Join a relative directory and a child name. */
export function joinRelative(dir: string | null | undefined, name: string): string {
  const base = (dir ?? '').replace(/\\/g, '/').replace(/^\.\/?/, '').replace(/\/+$/, '');
  return base ? `${base}/${name}` : name;
}
