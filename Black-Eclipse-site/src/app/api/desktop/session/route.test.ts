import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { promises as fs } from "fs";
import os from "os";
import path from "path";

import { GET, POST } from "@/app/api/desktop/session/route";

let dir: string;
let file: string;

function req(event: string, tab?: string, method = "GET") {
  const params = new URLSearchParams({ event });
  if (tab) params.set("tab", tab);
  return new Request(`http://localhost/api/desktop/session?${params}`, { method });
}

async function read() {
  return JSON.parse(await fs.readFile(file, "utf8"));
}

beforeEach(async () => {
  dir = await fs.mkdtemp(path.join(os.tmpdir(), "be-desktop-"));
  file = path.join(dir, "session.json");
  process.env.BE_DESKTOP_HEARTBEAT_FILE = file;
});

afterEach(async () => {
  delete process.env.BE_DESKTOP_HEARTBEAT_FILE;
  await fs.rm(dir, { recursive: true, force: true });
});

describe("/api/desktop/session", () => {
  it("is inert when the launcher did not set a heartbeat file", async () => {
    delete process.env.BE_DESKTOP_HEARTBEAT_FILE;
    const res = await GET(req("alive", "tab1"));
    expect(res.status).toBe(204);
  });

  it("refcounts tabs so closing one does not end the session", async () => {
    await POST(req("alive", "tab-a", "POST"));
    await GET(req("alive", "tab-b"));
    expect(Object.keys((await read()).tabs)).toEqual(expect.arrayContaining(["tab-a", "tab-b"]));

    await GET(req("leave", "tab-a"));
    const afterOne = await read();
    expect(Object.keys(afterOne.tabs)).toEqual(["tab-b"]);
    expect(afterOne.event).toBe("leave");

    await GET(req("leave", "tab-b"));
    const afterAll = await read();
    expect(afterAll.tabs).toBeUndefined();
    expect(afterAll.event).toBe("leave");
  });

  it("keeps legacy single-tab semantics for a cached page with no tab id", async () => {
    await GET(req("alive"));
    const state = await read();
    expect(state.event).toBe("alive");
    expect(state.tabs).toBeUndefined();
  });
});
