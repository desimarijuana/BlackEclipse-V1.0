import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { GET, POST } from "./route";
import { manifestPath, sitePackagesDir } from "@/lib/desktop/packs";

const cleanups: string[] = [];

function tempRoot(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "be-packs-route-"));
  cleanups.push(dir);
  return dir;
}

function request(body: unknown): Request {
  return new Request("http://127.0.0.1:3100/api/desktop/packs", {
    method: "POST",
    headers: { "content-type": "application/json", host: "127.0.0.1:3100" },
    body: JSON.stringify(body),
  });
}

const MANIFEST = {
  schema: 1,
  version: "1.0.0",
  repository: "owner/repo",
  allowedHosts: ["github.com"],
  packs: [
    { name: "browser", packages: ["playwright"], zip: "browser.zip", zipBytes: 10, sha256: "a".repeat(64) },
    { name: "charts", packages: ["plotly"], zip: "charts.zip", zipBytes: 20, sha256: "b".repeat(64) },
  ],
};

afterEach(() => {
  delete process.env.BE_APP_ROOT;
  delete process.env.BE_PACK_BASE_URL;
  while (cleanups.length) {
    const dir = cleanups.pop();
    if (dir) fs.rmSync(dir, { recursive: true, force: true });
  }
});

describe("GET /api/desktop/packs", () => {
  it("answers 200 and reports unsupported when this build has no manifest", async () => {
    process.env.BE_APP_ROOT = tempRoot();
    const res = await GET();
    const body = (await res.json()) as { supported: boolean; reason?: string };
    expect(res.status).toBe(200);
    expect(body.supported).toBe(false);
    expect(body.reason).toBeTruthy();
  });

  it("lists every pack for a packaged install", async () => {
    const root = tempRoot();
    fs.mkdirSync(sitePackagesDir(root), { recursive: true });
    fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
    fs.writeFileSync(manifestPath(root), JSON.stringify(MANIFEST));
    process.env.BE_APP_ROOT = root;

    const res = await GET();
    const body = (await res.json()) as {
      supported: boolean;
      packs: Array<{ name: string; installed: boolean; downloadable: boolean }>;
    };
    expect(body.supported).toBe(true);
    expect(body.packs.map((p) => p.name)).toEqual(["browser", "charts"]);
    expect(body.packs.every((p) => p.installed === false && p.downloadable)).toBe(true);
  });
});

describe("POST /api/desktop/packs", () => {
  it("rejects a body that names no action", async () => {
    process.env.BE_APP_ROOT = tempRoot();
    const res = await POST(request({ pack: "browser" }));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toMatch(/action/i);
  });

  it("404s a pack the manifest does not contain", async () => {
    const root = tempRoot();
    fs.mkdirSync(sitePackagesDir(root), { recursive: true });
    fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
    fs.writeFileSync(manifestPath(root), JSON.stringify(MANIFEST));
    process.env.BE_APP_ROOT = root;

    const res = await POST(request({ action: "install", pack: "not-a-pack" }));
    expect(res.status).toBe(404);
  });

  it("refuses a traversal pack name", async () => {
    const root = tempRoot();
    fs.mkdirSync(sitePackagesDir(root), { recursive: true });
    fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
    fs.writeFileSync(manifestPath(root), JSON.stringify(MANIFEST));
    process.env.BE_APP_ROOT = root;

    const res = await POST(request({ action: "install", pack: "../../etc" }));
    expect(res.status).toBe(400);
  });
});
