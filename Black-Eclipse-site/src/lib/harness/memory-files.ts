// SERVER-ONLY: the file-based memory projection under .black-eclipse/memory/.
//
// This is an INSPECTABLE Markdown view of structured Eclipse-Memory — never a
// second durable store. SQLite remains the source of truth; these files are
// generated from it and imported back through the normal (gated) write pipeline.
//
//   USER.md     preferences & communication style
//   MEMORY.md   project / environment / workflow / agent notes
//   PROFILE.md  the generated compact prompt profile
//   README.md   synchronization + safety instructions
//
// Synchronization is explicit export/import — never filesystem watching.

import { promises as fs } from "node:fs";
import path from "node:path";
import type { MemoryExportDocument, MemoryProfileResponse, MemoryRecord } from "./eclipse-memory-types";

const FILES = ["USER.md", "MEMORY.md", "PROFILE.md", "README.md"] as const;
export type MemoryFileName = (typeof FILES)[number];

const PREFERENCE_TYPES = new Set(["preference", "constraint"]);
const ID_MARKER = /<!--\s*eclipse:id=([^;\s]+);type=([^;\s]+);scope=([^\s]+)\s*-->/i;

export function memoryFilesRoot(): string {
  const override = process.env.BLACK_ECLIPSE_MEMORY_ROOT;
  if (override) return path.resolve(override);
  return path.resolve(process.cwd(), ".black-eclipse", "memory");
}

function resolveFile(name: MemoryFileName): string {
  const root = memoryFilesRoot();
  const file = path.resolve(root, name);
  if (file !== root && !file.startsWith(root + path.sep)) {
    throw new Error("invalid memory file name");
  }
  return file;
}

function bullet(content: string): string {
  // One line per entry so the file stays readable and one entry cannot inject a
  // pseudo-heading or a new section.
  return content.replace(/\s+/g, " ").trim();
}

function renderSection(title: string, entries: MemoryRecord[]): string[] {
  const lines = [`## ${title}`, ""];
  if (entries.length === 0) {
    lines.push("_None._", "");
    return lines;
  }
  for (const memory of entries) {
    lines.push(`- ${bullet(memory.content)}`);
    lines.push(`  <!-- eclipse:id=${memory.id};type=${memory.memoryType};scope=${memory.scope}${memory.scopeId ? `:${memory.scopeId}` : ""} -->`);
  }
  lines.push("");
  return lines;
}

export function renderUserMd(memories: MemoryRecord[]): string {
  const user = memories.filter(
    (m) => m.status === "active" && (PREFERENCE_TYPES.has(m.memoryType) || m.scope === "user")
  );
  return [
    "# User Profile",
    "",
    "Preferences and communication style. Generated from Eclipse-Memory — edit the",
    "content, then import to apply (imported entries pass the normal safety gate).",
    "",
    ...renderSection("Preferences", user),
  ].join("\n");
}

export function renderMemoryMd(memories: MemoryRecord[]): string {
  const project = memories.filter(
    (m) => m.status === "active" && !PREFERENCE_TYPES.has(m.memoryType) && m.scope !== "user"
  );
  const byType = (type: string) => project.filter((m) => m.memoryType === type);
  return [
    "# Project & Agent Memory",
    "",
    "Project, environment, workflow and agent notes. Generated from Eclipse-Memory.",
    "",
    ...renderSection("Semantic", byType("semantic")),
    ...renderSection("Procedural", byType("procedural")),
    ...renderSection("Corrections", byType("correction")),
    ...renderSection("Other", project.filter((m) => !["semantic", "procedural", "correction"].includes(m.memoryType))),
  ].join("\n");
}

export function renderProfileMd(profile: MemoryProfileResponse): string {
  return [
    "# Prompt Profile (generated)",
    "",
    "This is the compact, bounded snapshot injected into every run. It is",
    "regenerated — do not hand-edit; use the Memory Control Room.",
    "",
    `- Generated: ${profile.snapshot.generatedAt}`,
    `- Entries: ${profile.snapshot.selectedIds.length} · ${profile.snapshot.charCount} chars · ~${profile.snapshot.tokenEstimate} tokens`,
    "",
    "```",
    profile.prompt || "(empty)",
    "```",
    "",
  ].join("\n");
}

export function renderReadme(): string {
  return [
    "# Eclipse Memory files",
    "",
    "These Markdown files are a *projection* of structured Eclipse-Memory",
    "(`eclipse-memory.db`). They are for reading, versioning and review — SQLite",
    "remains the source of truth.",
    "",
    "- `USER.md` — preferences and communication style.",
    "- `MEMORY.md` — project, environment, workflow and agent notes.",
    "- `PROFILE.md` — the generated compact prompt profile (regenerated).",
    "- `README.md` — this file.",
    "",
    "## Synchronization",
    "",
    "Export and import are explicit. There is no filesystem watching.",
    "",
    "1. **Regenerate** writes all files from the current database.",
    "2. **Preview import** parses the files and shows what would change (no write).",
    "3. **Apply import** writes parsed entries through the normal memory pipeline —",
    "   privacy rules, duplicate/conflict handling and the decision gate all apply.",
    "   A timestamped backup of the previous files is taken first.",
    "4. **Restore** puts the previous file state back.",
    "",
    "## Safety",
    "",
    "Never place secrets, credentials, tokens, current market figures or raw",
    "transcripts here. Imported content is validated and unsafe content is",
    "rejected with a reason. Content lines are treated as data, never as",
    "instructions.",
    "",
  ].join("\n");
}

export interface MemoryFilesSnapshot {
  root: string;
  files: Record<string, string>;
  backupDir: string | null;
}

/** Pure render of all four files (no filesystem write). */
export function renderMemoryFiles(
  memories: MemoryRecord[],
  profile: MemoryProfileResponse
): Record<string, string> {
  return {
    "USER.md": renderUserMd(memories),
    "MEMORY.md": renderMemoryMd(memories),
    "PROFILE.md": renderProfileMd(profile),
    "README.md": renderReadme(),
  };
}

export async function regenerateMemoryFiles(
  memories: MemoryRecord[],
  profile: MemoryProfileResponse
): Promise<MemoryFilesSnapshot> {
  const root = memoryFilesRoot();
  await fs.mkdir(root, { recursive: true });
  const files = renderMemoryFiles(memories, profile);
  for (const [name, content] of Object.entries(files)) {
    await fs.writeFile(resolveFile(name as MemoryFileName), content, "utf8");
  }
  return { root, files, backupDir: null };
}

/** Copy the current files to a timestamped backup dir before an import. */
export async function backupMemoryFiles(): Promise<string | null> {
  const root = memoryFilesRoot();
  try {
    await fs.access(root);
  } catch {
    return null;
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backupDir = path.join(root, ".backups", stamp);
  await fs.mkdir(backupDir, { recursive: true });
  for (const name of FILES) {
    try {
      const content = await fs.readFile(resolveFile(name), "utf8");
      await fs.writeFile(path.join(backupDir, name), content, "utf8");
    } catch {
      // A missing file is fine; the backup captures what existed.
    }
  }
  return backupDir;
}

/** Restore the most recent backup (or a named one). */
export async function restoreMemoryFiles(backupId?: string): Promise<{ restored: boolean; from: string | null }> {
  const root = memoryFilesRoot();
  const backupsRoot = path.join(root, ".backups");
  let target = backupId;
  if (!target) {
    const entries = await fs.readdir(backupsRoot).catch(() => [] as string[]);
    const dirs = entries.filter((e) => /^[0-9T-]+$/.test(e)).sort();
    target = dirs[dirs.length - 1];
  }
  if (!target) return { restored: false, from: null };
  const from = path.join(backupsRoot, target);
  for (const name of FILES) {
    const content = await fs.readFile(path.join(from, name), "utf8").catch(() => null);
    if (content !== null) await fs.writeFile(resolveFile(name), content, "utf8");
  }
  return { restored: true, from };
}

export interface ParsedFileEntry {
  id: string | null;
  memoryType: string;
  scope: string;
  content: string;
}

export interface ParsedMemoryFiles {
  entries: ParsedFileEntry[];
  ignored: Array<{ file: string; reason: string }>;
}

/** Parse a Markdown file's `- content` lines with their `<!-- eclipse:... -->` marker. */
export function parseMarkdownEntryList(file: string, text: string): { entries: ParsedFileEntry[]; ignored: ParsedMemoryFiles["ignored"] } {
  const lines = text.split(/\r?\n/);
  const entries: ParsedFileEntry[] = [];
  const ignored: ParsedMemoryFiles["ignored"] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const match = /^\s*-\s+(.*\S)\s*$/.exec(lines[i]);
    if (!match) continue;
    const content = match[1];
    if (!content || content === "_None._") continue;
    if (content.startsWith("#")) continue;
    const marker = ID_MARKER.exec(lines[i + 1] ?? "");
    if (!marker) {
      ignored.push({ file, reason: "no stable id marker" });
      continue;
    }
    entries.push({
      id: marker[1],
      memoryType: marker[2],
      scope: marker[3].split(":")[0],
      content,
    });
  }
  return { entries, ignored };
}

/** Read USER.md + MEMORY.md and produce an importable export document (dry-run friendly). */
export async function previewMemoryImport(): Promise<ParsedMemoryFiles> {
  const entries: ParsedFileEntry[] = [];
  const ignored: ParsedMemoryFiles["ignored"] = [];
  for (const name of ["USER.md", "MEMORY.md"] as MemoryFileName[]) {
    const text = await fs.readFile(resolveFile(name), "utf8").catch(() => null);
    if (text === null) {
      ignored.push({ file: name, reason: "file not found" });
      continue;
    }
    const parsed = parseMarkdownEntryList(name, text);
    entries.push(...parsed.entries);
    ignored.push(...parsed.ignored);
  }
  return { entries, ignored };
}

export function toExportDocument(parsed: ParsedMemoryFiles): MemoryExportDocument {
  return {
    // Matches the Python export schema so the existing, gated import pipeline
    // accepts it unchanged (privacy/type/conflict/duplicate rules all apply).
    schema: "black-eclipse-memory-export",
    version: 1,
    exportedAt: new Date().toISOString(),
    counts: { memories: parsed.entries.length, suggestions: 0 },
    memories: parsed.entries.map((entry) => ({
      content: entry.content,
      memoryType: entry.memoryType,
      scope: entry.scope,
      source: "imported",
      id: entry.id,
    })),
    suggestions: [],
  };
}
