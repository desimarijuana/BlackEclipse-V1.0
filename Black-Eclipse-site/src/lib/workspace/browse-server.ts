// ── Server-side folder browsing for the picker (Node) ────────────────────────
//
// The folder picker is an operator UI on the machine that runs the app. Its
// browse + create actions are plain, bounded filesystem reads/writes, so they
// run here instead of through the Python agent runtime: a runtime restart must
// not freeze the picker. Approval of a folder as a workspace ROOT still goes
// through the runtime's trusted-root store — that is the widening act, and it
// stays on the one authority.
//
// Server-only: never import this from a client component.

import { existsSync, mkdirSync, readdirSync, realpathSync, statSync } from "node:fs";
import path from "node:path";

export const MAX_BROWSE_ENTRIES = 2000;
const MAX_FOLDER_NAME = 128;

export interface BrowseEntry {
  name: string;
  path: string;
  isDir: boolean;
  hidden: boolean;
}

export interface BrowseResult {
  path: string | null;
  parent: string | null;
  entries: BrowseEntry[];
  truncated: boolean;
  reason: string | null;
}

function driveRoots(): BrowseEntry[] {
  if (process.platform !== "win32") {
    return [{ name: "/", path: "/", isDir: true, hidden: false }];
  }
  const roots: BrowseEntry[] = [];
  for (const letter of "ABCDEFGHIJKLMNOPQRSTUVWXYZ") {
    const base = `${letter}:\\`;
    if (existsSync(base)) roots.push({ name: base, path: base, isDir: true, hidden: false });
  }
  return roots;
}

function parentOf(target: string): string | null {
  const parent = path.dirname(target);
  return parent === target ? null : parent;
}

/** List the DIRECT children of a folder (or the drive roots when path is empty). */
export function browseDirectory(target?: string | null): BrowseResult {
  if (!target) {
    return { path: null, parent: null, entries: driveRoots(), truncated: false, reason: null };
  }
  let resolved: string;
  try {
    resolved = realpathSync(target);
  } catch {
    return { path: target, parent: null, entries: [], truncated: false, reason: "That location could not be opened." };
  }
  let isDir = false;
  try {
    isDir = statSync(resolved).isDirectory();
  } catch {
    /* treated below */
  }
  if (!isDir) {
    return { path: resolved, parent: parentOf(resolved), entries: [], truncated: false, reason: "That location is not a folder." };
  }

  const entries: BrowseEntry[] = [];
  let truncated = false;
  try {
    for (const entry of readdirSync(resolved, { withFileTypes: true })) {
      if (entries.length >= MAX_BROWSE_ENTRIES) {
        truncated = true;
        break;
      }
      const full = path.join(resolved, entry.name);
      let childIsDir = entry.isDirectory();
      if (entry.isSymbolicLink()) {
        try {
          childIsDir = statSync(full).isDirectory();
        } catch {
          childIsDir = false;
        }
      }
      entries.push({ name: entry.name, path: full, isDir: childIsDir, hidden: entry.name.startsWith(".") });
    }
  } catch {
    return { path: resolved, parent: parentOf(resolved), entries: [], truncated: false, reason: "That folder could not be read." };
  }
  entries.sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1));
  return { path: resolved, parent: parentOf(resolved), entries, truncated, reason: null };
}

/** Create ONE folder directly under `parent` (a single leaf, never a path). */
export function createDirectory(parent: string, name: string): { path: string; name: string; parent: string } {
  const leaf = String(name ?? "").trim();
  if (!leaf || leaf === "." || leaf === ".." || leaf.includes("/") || leaf.includes("\\")) {
    throw new Error("Enter a folder name without a path.");
  }
  if (leaf.length > MAX_FOLDER_NAME) throw new Error("That folder name is too long.");
  if (!parent) throw new Error("Choose a drive or folder first.");

  let base: string;
  try {
    base = realpathSync(parent);
  } catch {
    throw new Error("That location could not be opened.");
  }
  try {
    if (!statSync(base).isDirectory()) throw new Error("not a directory");
  } catch {
    throw new Error("That location is not a folder.");
  }

  const target = path.join(base, leaf);
  try {
    mkdirSync(target);
  } catch (err) {
    // Idempotent for an existing folder; a file with that name is refused.
    try {
      if (!statSync(target).isDirectory()) throw new Error("not a directory");
    } catch {
      const code = (err as NodeJS.ErrnoException).code;
      throw new Error(code === "EEXIST" ? "A file with that name already exists." : `That folder could not be created: ${(err as Error).message}`);
    }
  }
  return { path: target, name: leaf, parent: base };
}
