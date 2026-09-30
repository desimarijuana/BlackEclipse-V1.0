import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  applyFileEdit,
  detectExternalDrift,
  MemoryFileDriftError,
  MemoryFileUnreadableError,
  parseMarkdownEntryList,
  readMemoryFileStrict,
  renderUserMd,
  safeWriteProjection,
} from "./memory-files";
import type { MemoryRecord } from "./eclipse-memory-types";
import os from "node:os";
import path from "node:path";
import { promises as fs } from "node:fs";

// Milestone 3 — file-projection data-loss guards. The projection is hand-editable
// and shell-appendable, so writes must never silently destroy content.

function memory(overrides: Partial<MemoryRecord>): MemoryRecord {
  return {
    id: "mem_1",
    memoryType: "preference",
    scope: "user",
    scopeId: "u1",
    subject: null,
    content: "User prefers concise answers",
    source: "explicit_user",
    sourceRunId: null,
    confidence: 0.9,
    importance: 0.5,
    status: "active",
    verification: "unverified",
    createdBy: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-02T00:00:00Z",
    lastAccessedAt: null,
    accessCount: 0,
    expiresAt: null,
    supersededBy: null,
    reviewedAt: null,
    reviewStatus: null,
    ...overrides,
  };
}

const ROOT = path.join(os.tmpdir(), `be-memfiles-m3-${process.pid}-${Date.now()}`);
const USER = path.join(ROOT, "USER_PROFILE.md");

beforeEach(async () => {
  process.env.BLACK_ECLIPSE_MEMORY_ROOT = ROOT;
  delete process.env.BLACK_ECLIPSE_MEMORY_HISTORY_ROOT;
  await fs.rm(ROOT, { recursive: true, force: true });
  await fs.mkdir(ROOT, { recursive: true });
});
afterEach(async () => {
  await fs.rm(ROOT, { recursive: true, force: true });
});

describe("memory-files data-loss guards (M3)", () => {
  it("strips a leading UTF-8 BOM on read", async () => {
    await fs.writeFile(USER, "\uFEFF" + renderUserMd([memory({ id: "mem_1" })]), "utf8");
    const text = await readMemoryFileStrict(USER);
    expect(text?.startsWith("\uFEFF")).toBe(false);
    // The BOM must not glue itself to the first entry marker/content.
    const { entries } = parseMarkdownEntryList("USER_PROFILE.md", text ?? "");
    expect(entries[0].id).toBe("mem_1");
  });

  it("BOM-prefixed file round-trips and dedups correctly", async () => {
    const rendered = renderUserMd([memory({ id: "mem_1" })]);
    await fs.writeFile(USER, "\uFEFF" + rendered, "utf8");
    const result = await applyFileEdit({
      operation: "replace", file: "USER_PROFILE.md", memoryId: "mem_1",
      expectedVersion: "2026-01-02T00:00:00Z", content: "User prefers detailed answers",
    });
    expect(result.ok).toBe(true);
    const after = await fs.readFile(USER, "utf8");
    expect(after).toContain("User prefers detailed answers");
    expect(after.startsWith("\uFEFF")).toBe(false);
  });

  it("refuses to write an existing-but-unreadable file and leaves it untouched", async () => {
    // A directory at the file path is unreadable as a file (EISDIR).
    await fs.mkdir(USER, { recursive: true });
    await expect(safeWriteProjection("USER_PROFILE.md", "new content")).rejects.toBeInstanceOf(
      MemoryFileUnreadableError
    );
    const stat = await fs.stat(USER);
    expect(stat.isDirectory()).toBe(true);
  });

  it("applyFileEdit refuses an unreadable file without changing it", async () => {
    await fs.mkdir(USER, { recursive: true });
    const result = await applyFileEdit({ operation: "add", file: "USER_PROFILE.md", content: "x" });
    expect(result.ok).toBe(false);
    expect(result.error).toContain("could not be read");
  });

  it("detects external drift and snapshots raw bytes to a .bak", async () => {
    // A shell append: a bullet with no id marker.
    const drifted = `${renderUserMd([memory({ id: "mem_1" })])}\n- appended by shell script\n`;
    await fs.writeFile(USER, drifted, "utf8");
    expect(detectExternalDrift("USER_PROFILE.md", drifted)).toBe(true);

    let error: unknown;
    try {
      await safeWriteProjection("USER_PROFILE.md", renderUserMd([memory({ id: "mem_2" })]));
    } catch (err) {
      error = err;
    }
    expect(error).toBeInstanceOf(MemoryFileDriftError);
    const drift = error as MemoryFileDriftError;
    expect(drift.remediation).toContain("Nothing was overwritten");

    // The original was not overwritten, and the .bak holds the raw bytes.
    expect(await fs.readFile(USER, "utf8")).toBe(drifted);
    const backup = await fs.readFile(drift.backupPath, "utf8");
    expect(backup).toBe(drifted);
  });

  it("does not flag a projection-written file as drift", () => {
    const clean = renderUserMd([memory({ id: "mem_1" }), memory({ id: "mem_2", content: "Another" })]);
    expect(detectExternalDrift("USER_PROFILE.md", clean)).toBe(false);
  });

  it("does not apply drift detection to generated non-entry files", () => {
    const readme = "# README\n\n- a bare bullet\n- another\n";
    expect(detectExternalDrift("README.md", readme)).toBe(false);
  });

  it("consolidate keeps a non-empty file non-empty (never wipes)", async () => {
    const text = [
      "# Memory", "",
      "- Project uses pnpm",
      "  <!-- eclipse:id=m1;type=semantic;scope=general -->",
      "- Project uses pnpm",
      "  <!-- eclipse:id=m2;type=semantic;scope=general -->",
    ].join("\n");
    await fs.writeFile(path.join(ROOT, "MEMORY.md"), text, "utf8");
    const result = await applyFileEdit({ operation: "consolidate", file: "MEMORY.md" });
    expect(result.ok).toBe(true);
    expect(result.entries).toHaveLength(1);
    const after = await fs.readFile(path.join(ROOT, "MEMORY.md"), "utf8");
    expect(after).toContain("Project uses pnpm");
  });

  it("a deliberate single removal still works (replace path is intact)", async () => {
    await fs.writeFile(USER, renderUserMd([memory({ id: "mem_1" })]), "utf8");
    const result = await applyFileEdit({
      operation: "replace", file: "USER_PROFILE.md", memoryId: "mem_1",
      expectedVersion: "2026-01-02T00:00:00Z", content: "Changed",
    });
    expect(result.ok).toBe(true);
  });

  it("strict decoding refuses undecodable bytes", async () => {
    // 0xFF is never valid UTF-8.
    await fs.writeFile(USER, Buffer.from([0xff, 0xfe, 0x00]));
    await expect(readMemoryFileStrict(USER)).rejects.toBeTruthy();
  });

  it("a missing file reads as null (not an error)", async () => {
    expect(await readMemoryFileStrict(path.join(ROOT, "NOPE.md"))).toBeNull();
  });

  // ── Cross-cutting: the projection survives backup/restore (Phase 3) ────────

  it("backup and restore round-trip preserves entry identity and dedups", async () => {
    const clean = renderUserMd([memory({ id: "mem_1" }), memory({ id: "mem_2", content: "Another" })]);
    await fs.writeFile(USER, clean, "utf8");
    const { backupMemoryFiles, restoreMemoryFiles } = await import("./memory-files");
    const backupDir = await backupMemoryFiles();
    expect(backupDir).not.toBeNull();
    // Perturb the live file, then restore.
    await fs.writeFile(USER, renderUserMd([memory({ id: "mem_1", content: "Changed" })]), "utf8");
    const restored = await restoreMemoryFiles();
    expect(restored.restored).toBe(true);
    const text = await readMemoryFileStrict(USER);
    const { entries } = parseMarkdownEntryList("USER_PROFILE.md", text ?? "");
    expect(entries.map((e) => e.id)).toEqual(["mem_1", "mem_2"]);
  });

  it("a BOM-prefixed external drift is still detected after BOM strip", async () => {
    const drifted = "\uFEFF" + `${renderUserMd([memory({ id: "mem_1" })])}\n- shell appended\n`;
    await fs.writeFile(USER, drifted, "utf8");
    const text = await readMemoryFileStrict(USER);
    expect(detectExternalDrift("USER_PROFILE.md", text ?? "")).toBe(true);
  });
});
