import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

// Checkpoints are real files under the session root. Point the store at a temp
// directory so the test never touches the user's .black-eclipse folder.

let tempRoot: string;

beforeEach(async () => {
  tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "be-checkpoints-"));
  process.env.BLACK_ECLIPSE_SESSION_ROOT = tempRoot;
});

afterEach(async () => {
  delete process.env.BLACK_ECLIPSE_SESSION_ROOT;
  await fs.rm(tempRoot, { recursive: true, force: true });
});

async function store() {
  return import("./checkpoint-store");
}

const messages = [
  { id: "1", role: "user", content: "price of AAPL?" },
  { id: "2", role: "assistant", content: "AAPL is 338.55." },
];

describe("checkpoint-store", () => {
  it("creates, lists and reads a checkpoint", async () => {
    const s = await store();
    const created = await s.createCheckpoint("chat1", "Before asking", messages);
    expect(created.messageCount).toBe(2);

    const list = await s.listCheckpoints("chat1");
    expect(list.length).toBe(1);
    expect(list[0].label).toBe("Before asking");

    const snapshot = await s.readCheckpoint("chat1", created.id);
    expect(snapshot?.messages).toEqual(messages);
  });

  it("rejects an invalid chat id (path-traversal guard)", async () => {
    const s = await store();
    await expect(s.createCheckpoint("../../etc", "x", messages)).rejects.toThrow();
  });

  it("returns an empty list for an unknown conversation", async () => {
    const s = await store();
    expect(await s.listCheckpoints("never-seen")).toEqual([]);
  });

  it("deletes a checkpoint", async () => {
    const s = await store();
    const cp = await s.createCheckpoint("chat2", "x", messages);
    await s.deleteCheckpoint("chat2", cp.id);
    expect(await s.listCheckpoints("chat2")).toEqual([]);
  });

  it("returns null for a missing checkpoint", async () => {
    const s = await store();
    expect(await s.readCheckpoint("chat3", "nope")).toBeNull();
  });

  it("sanitizes the label and caps its length", async () => {
    const s = await store();
    const cp = await s.createCheckpoint("chat4", "line1\nline2", messages);
    expect(cp.label).not.toContain("\n");
    const long = await s.createCheckpoint("chat4", "x".repeat(500), messages);
    expect(long.label.length).toBeLessThanOrEqual(120);
  });

  it("lists newest first", async () => {
    const s = await store();
    await s.createCheckpoint("chat5", "first", messages);
    await new Promise((r) => setTimeout(r, 5));
    await s.createCheckpoint("chat5", "second", messages);
    const list = await s.listCheckpoints("chat5");
    expect(list[0].label).toBe("second");
  });
});
