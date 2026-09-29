// SERVER-ONLY: the file-based memory projection under .black-eclipse/memory/.
//
// This is an INSPECTABLE Markdown view of structured Eclipse-Memory — never a
// second durable store. SQLite remains the source of truth; these files are
// generated from it and imported back through the normal (gated) write pipeline.
//
//   USER_PROFILE.md    preferences & communication style
//   MEMORY.md          durable agent/environment facts
//   PROJECT_MEMORY.md  project conventions
//   SKILLS.md          human-readable skill index
//   PROFILE.md         the generated compact prompt profile
//   README.md          synchronization + safety instructions
//
// Synchronization is explicit export/import — never filesystem watching.

import { promises as fs } from "node:fs";
import path from "node:path";
import type { MemoryExportDocument, MemoryProfileResponse, MemoryRecord } from "./eclipse-memory-types";

const FILES = ["USER_PROFILE.md", "MEMORY.md", "PROJECT_MEMORY.md", "SKILLS.md", "PROFILE.md", "README.md"] as const;
export type MemoryFileName = (typeof FILES)[number];

// Legacy names from the earlier projection; still read so an existing install
// migrates cleanly on the next regenerate.
const LEGACY_FILES: Record<string, MemoryFileName> = {
  "USER.md": "USER_PROFILE.md",
  "MEMORY.md": "MEMORY.md",
  "PROFILE.md": "PROFILE.md",
  "README.md": "README.md",
};

const PREFERENCE_TYPES = new Set(["preference", "constraint"]);
// Stable entry marker. `version` (the memory's version/updated stamp) is included
// so a stale targeted edit can be rejected before it is applied.
const ID_MARKER = /<!--\s*eclipse:id=([^;\s]+);type=([^;\s]+);scope=([^;\s]+)(?:;version=([^;\s]+))?\s*-->/i;

// The projections whose every bullet entry carries an `eclipse:` id marker.
// Drift detection applies only to these; the generated README/SKILLS/PROFILE
// files legitimately contain bare bullets.
const ENTRY_FILES: MemoryFileName[] = ["USER_PROFILE.md", "MEMORY.md", "PROJECT_MEMORY.md"];

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
    const version = memory.updatedAt ?? memory.createdAt ?? "";
    lines.push(`  <!-- eclipse:id=${memory.id};type=${memory.memoryType};scope=${memory.scope}${memory.scopeId ? `:${memory.scopeId}` : ""}${version ? `;version=${version}` : ""} -->`);
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

export function renderProjectMemoryMd(memories: MemoryRecord[]): string {
  const project = memories.filter(
    (m) => m.status === "active" && !PREFERENCE_TYPES.has(m.memoryType) && m.scope !== "user"
  );
  return [
    "# Project Memory",
    "",
    "Project conventions and workflow/environment notes. Generated from",
    "Eclipse-Memory.",
    "",
    ...renderSection("Conventions", project),
  ].join("\n");
}

export function renderSkillsMd(skills: Array<{ id: string; name: string; status: string; version?: string }>): string {
  const lines = [
    "# Skills (human-readable index)",
    "",
    "A read-only index of installed skills. Skills are NOT editable from these",
    "files — use the Skills Control Room. Machine-readable definitions live in",
    "`python/harness/skills/library/` and `eclipse-memory.db`.",
    "",
  ];
  if (skills.length === 0) {
    lines.push("_None._", "");
  } else {
    for (const skill of skills) {
      lines.push(`- ${skill.name} (\`${skill.id}\`${skill.version ? ` v${skill.version}` : ""}) — ${skill.status}`);
    }
    lines.push("");
  }
  return lines.join("\n");
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
    "- `USER_PROFILE.md` — preferences and communication style.",
    "- `MEMORY.md` — durable agent/environment facts.",
    "- `PROJECT_MEMORY.md` — project conventions.",
    "- `SKILLS.md` — a read-only human-readable skill index.",
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

/** Pure render of all files (no filesystem write). */
export function renderMemoryFiles(
  memories: MemoryRecord[],
  profile: MemoryProfileResponse,
  skills: Array<{ id: string; name: string; status: string; version?: string }> = []
): Record<string, string> {
  return {
    "USER_PROFILE.md": renderUserMd(memories),
    "MEMORY.md": renderMemoryMd(memories),
    "PROJECT_MEMORY.md": renderProjectMemoryMd(memories),
    "SKILLS.md": renderSkillsMd(skills),
    "PROFILE.md": renderProfileMd(profile),
    "README.md": renderReadme(),
  };
}

/**
 * Atomic write: write to a sibling temp file, fsync, then rename over the
 * target. A crash mid-write leaves the original intact. Never a partial file.
 */
export async function atomicWriteFile(target: string, content: string): Promise<void> {
  const dir = path.dirname(target);
  await fs.mkdir(dir, { recursive: true });
  const tmp = path.join(dir, `.${path.basename(target)}.${process.pid}.${Date.now()}.tmp`);
  const handle = await fs.open(tmp, "w");
  try {
    await handle.writeFile(content, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
  await fs.rename(tmp, target);
}

// ── Read-side guards (Milestone 3) ──────────────────────────────────────────
//
// The projection files are hand-editable, so the reader must not silently
// destroy content it cannot understand. Three data-loss classes are guarded:
// an unreadable file is never treated as empty; a leading UTF-8 BOM is stripped
// so it cannot glue to the first entry; decoding is strict.

const BOM = "\uFEFF";

/** Read a projection file, stripping a leading UTF-8 BOM. Strict decoding. */
export async function readMemoryFileStrict(target: string): Promise<string | null> {
  // `null` means the file genuinely does not exist. Any other read failure
  // (permissions, EISDIR, undecodable bytes) is rethrown so the caller refuses
  // to write rather than treating it as an empty file.
  let buffer: Buffer;
  try {
    buffer = await fs.readFile(target);
  } catch (err) {
    if ((err as NodeJS.ErrnoException)?.code === "ENOENT") return null;
    throw err;
  }
  // Strict decode: invalid UTF-8 throws rather than silently substituting U+FFFD
  // (a lossy decode followed by a save would persist the loss).
  const text = new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  return text.startsWith(BOM) ? text.slice(BOM.length) : text;
}

export class MemoryFileUnreadableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MemoryFileUnreadableError";
  }
}

export class MemoryFileDriftError extends Error {
  backupPath: string;
  remediation: string;
  constructor(message: string, backupPath: string, remediation: string) {
    super(message);
    this.name = "MemoryFileDriftError";
    this.backupPath = backupPath;
    this.remediation = remediation;
  }
}

/**
 * Detect whether an on-disk projection file would survive a round-trip through
 * the projection's own parser. A hand edit, a shell append or a foreign tool can
 * leave content the projection did not write; flushing over it would discard it.
 *
 * The check is structural: every non-header, non-empty line that looks like an
 * entry (`- …`) must carry a following `<!-- eclipse:… -->` marker. A file the
 * projection wrote always satisfies this.
 */
export function detectExternalDrift(file: MemoryFileName, text: string): boolean {
  // Only the entry-list projections have a marker-per-entry contract; the
  // generated README/SKILLS/PROFILE files legitimately contain bare bullets.
  if (!ENTRY_FILES.includes(file)) return false;
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!/^\s*-\s+\S/.test(line)) continue;
    const content = line.replace(/^\s*-\s+/, "").trim();
    if (content === "_None._") continue;
    if (!ID_MARKER.test(lines[i + 1] ?? "")) return true;
  }
  return false;
}

async function snapshotDrift(target: string, raw: string): Promise<string> {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backupPath = `${target}.${stamp}.bak`;
  await fs.writeFile(backupPath, raw, "utf8");
  return backupPath;
}

/**
 * Write a projection file with the read-side guards applied.
 *
 *  * refuses to write when the target exists but cannot be read (never silently
 *    wipes it);
 *  * refuses to flush over externally-drifted content, snapshotting the raw
 *    bytes to a timestamped `.bak` and returning a remediation instruction;
 *  * strips a leading BOM before parsing so it cannot corrupt entry identity.
 */
export async function safeWriteProjection(
  file: MemoryFileName,
  content: string,
): Promise<{ written: boolean; drift?: boolean; backupPath?: string; remediation?: string }> {
  const target = resolveFile(file);
  let existing: string | null;
  try {
    existing = await readMemoryFileStrict(target);
  } catch (err) {
    throw new MemoryFileUnreadableError(
      `refusing to write ${file}: the existing file could not be read ` +
        `(${err instanceof Error ? err.message : String(err)})`
    );
  }
  if (existing !== null && detectExternalDrift(file, existing)) {
    const backupPath = await snapshotDrift(target, existing);
    const remediation =
      `The on-disk ${file} contains content this projection did not write ` +
      `(a hand edit, a shell append, or another tool). Nothing was overwritten. ` +
      `Raw bytes were saved to ${backupPath}. Reconcile the file — regenerate from ` +
      `the database, or import it through the gated pipeline — then retry.`;
    throw new MemoryFileDriftError(remediation, backupPath, remediation);
  }
  await atomicWriteFile(target, content);
  return { written: true };
}

export async function regenerateMemoryFiles(
  memories: MemoryRecord[],
  profile: MemoryProfileResponse,
  skills: Array<{ id: string; name: string; status: string; version?: string }> = []
): Promise<MemoryFilesSnapshot> {
  const root = memoryFilesRoot();
  await fs.mkdir(root, { recursive: true });
  // Backup the CURRENT state before overwriting, so a regenerate is reversible.
  const backupDir = await backupMemoryFiles();
  const files = renderMemoryFiles(memories, profile, skills);
  for (const [name, content] of Object.entries(files)) {
    // Guarded write: refuses to wipe an unreadable file or clobber externally
    // drifted content (snapshotting it to a `.bak` first).
    await safeWriteProjection(name as MemoryFileName, content);
  }
  return { root, files, backupDir };
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
  version: string | null;
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
      version: marker[4] ?? null,
      content,
    });
  }
  return { entries, ignored };
}

// ── Targeted edits, history and rollback (M6) ───────────────────────────────

export type FileEditOperation =
  | "add"
  | "replace"
  | "archive"
  | "restore"
  | "merge"
  | "split"
  | "reorder"
  | "consolidate";

export interface FileEditRequest {
  operation: FileEditOperation;
  file: MemoryFileName;
  memoryId?: string;
  expectedVersion?: string;
  content?: string;
}

export interface FileEditResult {
  ok: boolean;
  error?: string;
  file?: MemoryFileName;
  /** The parsed entries the caller should route through the gated import pipeline. */
  entries?: ParsedFileEntry[];
}

export interface HistoryRevision {
  revision: string;
  at: string;
  actor: string;
  sourceRun: string | null;
  reviewId: string | null;
  reason: string;
  affectedIds: string[];
  parentRevision: string | null;
  before: string | null;
  after: string;
}

function historyRoot(): string {
  const override = process.env.BLACK_ECLIPSE_MEMORY_HISTORY_ROOT;
  if (override) return path.resolve(override);
  return path.join(memoryFilesRoot(), ".history");
}

/** Record one revision (before/after + actor + reason) with a parent link. */
export async function recordRevision(input: {
  file: MemoryFileName;
  before: string | null;
  after: string;
  actor: string;
  reason: string;
  affectedIds: string[];
  sourceRun?: string | null;
  reviewId?: string | null;
}): Promise<HistoryRevision> {
  const root = historyRoot();
  await fs.mkdir(root, { recursive: true });
  const previous = await listRevisions(input.file);
  const parentRevision = previous.length ? previous[previous.length - 1].revision : null;
  const at = new Date().toISOString();
  const revision = `rev_${at.replace(/[:.]/g, "-")}_${Math.random().toString(36).slice(2, 8)}`;
  const record: HistoryRevision = {
    revision,
    at,
    actor: input.actor,
    sourceRun: input.sourceRun ?? null,
    reviewId: input.reviewId ?? null,
    reason: input.reason,
    affectedIds: input.affectedIds,
    parentRevision,
    before: input.before,
    after: input.after,
  };
  await atomicWriteFile(path.join(root, `${input.file}.${revision}.json`), JSON.stringify(record, null, 2));
  return record;
}

export async function listRevisions(file: MemoryFileName): Promise<HistoryRevision[]> {
  const root = historyRoot();
  const entries = await fs.readdir(root).catch(() => [] as string[]);
  const revisions: HistoryRevision[] = [];
  for (const name of entries) {
    if (!name.startsWith(`${file}.`) || !name.endsWith(".json")) continue;
    const raw = await fs.readFile(path.join(root, name), "utf8").catch(() => null);
    if (raw === null) continue;
    try {
      revisions.push(JSON.parse(raw) as HistoryRevision);
    } catch {
      // A malformed revision is skipped, never fabricated.
    }
  }
  revisions.sort((a, b) => (a.at < b.at ? -1 : 1));
  return revisions;
}

/**
 * Apply a targeted edit to the Markdown projection.
 *
 * This parses the file, validates the requested operation (including the
 * `expectedVersion` precondition for a stale-edit rejection), records a backup
 * revision, writes atomically, and returns the resulting entries so the existing
 * GATED import pipeline applies them to structured memory. The file is never the
 * source of truth.
 */
export async function applyFileEdit(request: FileEditRequest, actor = "operator"): Promise<FileEditResult> {
  if (!FILES.includes(request.file)) return { ok: false, error: "unknown file" };
  const target = resolveFile(request.file);
  // Refuse to treat an existing-but-unreadable file as empty: that would wipe
  // it on save. A genuinely missing file (ENOENT) is `null` and is fine.
  let before: string | null;
  try {
    before = await readMemoryFileStrict(target);
  } catch (err) {
    return {
      ok: false,
      error:
        `refusing to edit ${request.file}: the existing file could not be read ` +
        `(${err instanceof Error ? err.message : String(err)}). Nothing was changed.`,
    };
  }
  const parsed = before === null ? { entries: [], ignored: [] } : parseMarkdownEntryList(request.file, before);
  const entries = [...parsed.entries];
  const index = request.memoryId ? entries.findIndex((e) => e.id === request.memoryId) : -1;

  const needsTarget = request.operation !== "add" && request.operation !== "consolidate";
  if (needsTarget && index < 0) {
    return { ok: false, error: `memory id ${request.memoryId ?? "(none)"} not found in ${request.file}` };
  }
  if (needsTarget && request.expectedVersion && entries[index].version !== request.expectedVersion) {
    return {
      ok: false,
      error: `stale edit: expected version ${request.expectedVersion}, found ${entries[index].version ?? "none"}`,
    };
  }

  const content = (request.content ?? "").trim();
  switch (request.operation) {
    case "add":
      if (!content) return { ok: false, error: "add requires content" };
      entries.push({ id: null, memoryType: "semantic", scope: "general", version: null, content });
      break;
    case "replace":
      if (!content) return { ok: false, error: "replace requires content" };
      entries[index] = { ...entries[index], content };
      break;
    case "archive":
    case "restore":
      // The projection is regenerated from structured memory; archive/restore are
      // applied through the memory API, not the file. Report that honestly.
      return { ok: false, error: `${request.operation} is a structured-memory action; use the Memory API` };
    case "merge": {
      const other = request.content ? entries.findIndex((e) => e.id === request.content) : -1;
      if (other < 0) return { ok: false, error: "merge requires a second memory id in `content`" };
      entries[index] = { ...entries[index], content: `${entries[index].content} ${entries[other].content}`.trim() };
      entries.splice(other, 1);
      break;
    }
    case "split": {
      if (!content) return { ok: false, error: "split requires the second half in `content`" };
      entries[index] = { ...entries[index], content: entries[index].content.replace(content, "").trim() };
      entries.push({ ...entries[index], id: null, content });
      break;
    }
    case "reorder": {
      const to = Number(request.content);
      if (!Number.isInteger(to) || to < 0 || to >= entries.length) return { ok: false, error: "reorder requires a valid index in `content`" };
      const [moved] = entries.splice(index, 1);
      entries.splice(to, 0, moved);
      break;
    }
    case "consolidate": {
      const seen = new Map<string, ParsedFileEntry>();
      const consolidated: ParsedFileEntry[] = [];
      for (const entry of entries) {
        const key = entry.content.toLowerCase().replace(/\s+/g, " ").trim();
        if (seen.has(key)) continue;
        seen.set(key, entry);
        consolidated.push(entry);
      }
      // A consolidation batch must never empty a previously non-empty file.
      // A deliberate single removal is the only wipe path.
      if (consolidated.length === 0 && parsed.entries.length > 0) {
        return {
          ok: false,
          error: "refusing to consolidate an existing non-empty file to empty; remove entries individually instead",
        };
      }
      entries.length = 0;
      entries.push(...consolidated);
      break;
    }
    default:
      return { ok: false, error: `unsupported operation ${request.operation}` };
  }

  const after = renderEditedList(request.file, before, entries);
  await fs.mkdir(memoryFilesRoot(), { recursive: true });
  await atomicWriteFile(target, after);
  await recordRevision({
    file: request.file, before, after, actor, reason: `file edit: ${request.operation}`,
    affectedIds: request.memoryId ? [request.memoryId] : [],
  });
  return { ok: true, file: request.file, entries };
}

function renderEditedList(file: MemoryFileName, before: string | null, entries: ParsedFileEntry[]): string {
  const header = before ? before.split(/\r?\n(?=- |## )/)[0].trimEnd() : `# ${file}`;
  const lines = [header, ""];
  for (const entry of entries) {
    lines.push(`- ${bullet(entry.content)}`);
    const version = entry.version ? `;version=${entry.version}` : "";
    lines.push(`  <!-- eclipse:id=${entry.id ?? ""};type=${entry.memoryType};scope=${entry.scope}${version} -->`);
  }
  lines.push("");
  return lines.join("\n");
}

/** Roll one file back to a named revision's `before` state (atomic). */
export async function rollbackFile(file: MemoryFileName, revision: string): Promise<{ restored: boolean; from: string | null }> {
  const revisions = await listRevisions(file);
  const target = revisions.find((r) => r.revision === revision);
  if (!target || target.before === null) return { restored: false, from: null };
  const current = await fs.readFile(resolveFile(file), "utf8").catch(() => null);
  await atomicWriteFile(resolveFile(file), target.before);
  await recordRevision({
    file, before: current, after: target.before, actor: "operator",
    reason: `rollback to ${revision}`, affectedIds: target.affectedIds,
  });
  return { restored: true, from: revision };
}

/** A unified-style diff of two text states (bounded, line-based). */
export function diffText(before: string, after: string): Array<{ type: "add" | "remove" | "same"; line: string }> {
  const a = before.split(/\r?\n/);
  const b = after.split(/\r?\n/);
  const out: Array<{ type: "add" | "remove" | "same"; line: string }> = [];
  const max = Math.max(a.length, b.length);
  for (let i = 0; i < max; i += 1) {
    if (a[i] === b[i]) out.push({ type: "same", line: a[i] ?? "" });
    else {
      if (a[i] !== undefined) out.push({ type: "remove", line: a[i] });
      if (b[i] !== undefined) out.push({ type: "add", line: b[i] });
    }
  }
  return out;
}

/** Read the memory files and produce an importable export document (dry-run friendly). */
export async function previewMemoryImport(): Promise<ParsedMemoryFiles> {
  const entries: ParsedFileEntry[] = [];
  const ignored: ParsedMemoryFiles["ignored"] = [];
  for (const name of ["USER_PROFILE.md", "MEMORY.md", "PROJECT_MEMORY.md"] as MemoryFileName[]) {
    let text: string | null;
    try {
      text = await readMemoryFileStrict(resolveFile(name));
    } catch (err) {
      // An unreadable file is NOT an empty file: report it rather than dropping
      // its content from the preview.
      ignored.push({ file: name, reason: `unreadable: ${err instanceof Error ? err.message : String(err)}` });
      continue;
    }
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
