import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyFileEdit,
  atomicWriteFile,
  diffText,
  listRevisions,
  parseMarkdownEntryList,
  rollbackFile,
  renderUserMd,
} from "./memory-files";
import type { MemoryRecord } from "./eclipse-memory-types";

// The M6 edit workflow: targeted edits with an expectedVersion guard, atomic
// writes, and structured history/rollback. Files are an inspectable projection;
// SQLite stays canonical.

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

// Use a temp root so the real .black-eclipse tree is never touched.
import os from "node:os";
import path from "node:path";
import { promises as fs } from "node:fs";

const ROOT = path.join(os.tmpdir(), `be-memfiles-${process.pid}-${Date.now()}`);

beforeEach(async () => {
  process.env.BLACK_ECLIPSE_MEMORY_ROOT = ROOT;
  delete process.env.BLACK_ECLIPSE_MEMORY_HISTORY_ROOT;
  await fs.rm(ROOT, { recursive: true, force: true });
});
afterEach(async () => {
  await fs.rm(ROOT, { recursive: true, force: true });
});

describe("memory-files edit workflow (M6)", () => {
  it("renders a versioned marker", () => {
    const text = renderUserMd([memory({ id: "mem_9", content: "Prefers dark mode", updatedAt: "2026-03-01T00:00:00Z" })]);
    expect(text).toContain("eclipse:id=mem_9;type=preference;scope=user:u1;version=2026-03-01T00:00:00Z");
  });

  it("atomicWriteFile leaves no partial file and replaces atomically", async () => {
    const target = path.join(ROOT, "USER_PROFILE.md");
    await atomicWriteFile(target, "first");
    await atomicWriteFile(target, "second");
    expect(await fs.readFile(target, "utf8")).toBe("second");
    const leftovers = (await fs.readdir(ROOT)).filter((n) => n.includes(".tmp"));
    expect(leftovers).toEqual([]);
  });

  it("applyFileEdit rejects a stale expectedVersion", async () => {
    const target = path.join(ROOT, "USER_PROFILE.md");
    await atomicWriteFile(target, renderUserMd([memory({ id: "mem_1" })]));
    const result = await applyFileEdit({
      operation: "replace", file: "USER_PROFILE.md", memoryId: "mem_1",
      expectedVersion: "wrong-version", content: "User prefers detailed answers",
    });
    expect(result.ok).toBe(false);
    expect(result.error).toContain("stale edit");
  });

  it("applyFileEdit replaces an entry and records a revision", async () => {
    const target = path.join(ROOT, "USER_PROFILE.md");
    await atomicWriteFile(target, renderUserMd([memory({ id: "mem_1" })]));
    const result = await applyFileEdit({
      operation: "replace", file: "USER_PROFILE.md", memoryId: "mem_1",
      expectedVersion: "2026-01-02T00:00:00Z", content: "User prefers detailed answers",
    });
    expect(result.ok).toBe(true);
    const after = await fs.readFile(target, "utf8");
    expect(after).toContain("User prefers detailed answers");
    const revisions = await listRevisions("USER_PROFILE.md");
    expect(revisions).toHaveLength(1);
    expect(revisions[0].affectedIds).toContain("mem_1");
  });

  it("rollbackFile restores a prior revision", async () => {
    const target = path.join(ROOT, "USER_PROFILE.md");
    await atomicWriteFile(target, renderUserMd([memory({ id: "mem_1", content: "Original" })]));
    await applyFileEdit({
      operation: "replace", file: "USER_PROFILE.md", memoryId: "mem_1",
      expectedVersion: "2026-01-02T00:00:00Z", content: "Changed",
    });
    const revisions = await listRevisions("USER_PROFILE.md");
    const restored = await rollbackFile("USER_PROFILE.md", revisions[0].revision);
    expect(restored.restored).toBe(true);
    expect(await fs.readFile(target, "utf8")).toContain("Original");
  });

  it("consolidate removes duplicate entries", async () => {
    const target = path.join(ROOT, "MEMORY.md");
    const text = [
      "# Memory", "",
      "- Project uses pnpm",
      "  <!-- eclipse:id=m1;type=semantic;scope=general -->",
      "- Project uses pnpm",
      "  <!-- eclipse:id=m2;type=semantic;scope=general -->",
    ].join("\n");
    await atomicWriteFile(target, text);
    const result = await applyFileEdit({ operation: "consolidate", file: "MEMORY.md" });
    expect(result.ok).toBe(true);
    expect(result.entries).toHaveLength(1);
  });

  it("diffText reports added and removed lines", () => {
    const diff = diffText("a\nb", "a\nc");
    expect(diff).toContainEqual({ type: "same", line: "a" });
    expect(diff).toContainEqual({ type: "remove", line: "b" });
    expect(diff).toContainEqual({ type: "add", line: "c" });
  });

  it("parseMarkdownEntryList still reads a marker without version", () => {
    const text = "- Prefers concise\n  <!-- eclipse:id=m;type=preference;scope=user -->";
    const { entries } = parseMarkdownEntryList("USER_PROFILE.md", text);
    expect(entries[0].version).toBeNull();
  });
});
