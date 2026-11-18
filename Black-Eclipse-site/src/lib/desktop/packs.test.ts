import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";
import {
  appRoot,
  isPackInstalled,
  isValidPackName,
  lastJob,
  manifestPath,
  packArchiveUrl,
  packStatuses,
  parsePackManifest,
  readPackManifest,
  removePack,
  sitePackagesDir,
  snapshot,
  startInstall,
} from "./packs";

const MANIFEST = {
  schema: 1,
  version: "1.2.3",
  repository: "owner/repo",
  allowedHosts: ["github.com", "objects.githubusercontent.com"],
  target: "win32-x64",
  packs: [
    { name: "browser", packages: ["playwright"], bytes: 105, zip: "browser.zip", zipBytes: 42, sha256: "abc" },
    { name: "charts", packages: ["plotly", "matplotlib"], bytes: 20, zip: "charts.zip", zipBytes: 9, sha256: "def" },
  ],
};

const cleanups: string[] = [];

function tempRoot(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "be-packs-"));
  cleanups.push(dir);
  return dir;
}

afterEach(() => {
  while (cleanups.length) {
    const dir = cleanups.pop();
    if (dir) fs.rmSync(dir, { recursive: true, force: true });
  }
  delete process.env.BE_PACK_BASE_URL;
  delete process.env.BE_APP_ROOT;
});

describe("pack manifest", () => {
  it("accepts the shipped shape and drops garbage", () => {
    const parsed = parsePackManifest({
      ...MANIFEST,
      packs: [
        ...MANIFEST.packs,
        { name: "Bad Name", packages: ["x"] },
        { name: "empty", packages: [] },
        { name: "traversal", packages: ["../../etc"] },
        "not an object",
      ],
    });
    expect(parsed).not.toBeNull();
    expect(parsed?.packs.map((p) => p.name)).toEqual(["browser", "charts"]);
    expect(parsed?.version).toBe("1.2.3");
    expect(parsed?.allowedHosts).toContain("github.com");
  });

  it("returns null for a broken manifest instead of throwing", () => {
    expect(parsePackManifest(null)).toBeNull();
    expect(parsePackManifest({})).toBeNull();
    expect(parsePackManifest({ packs: "nope" })).toBeNull();
  });

  it("defaults the allowlist when it is missing (never opens the gate)", () => {
    const parsed = parsePackManifest({ version: "1.0.0", repository: "a/b", packs: MANIFEST.packs });
    expect(parsed?.allowedHosts).toEqual(["github.com", "objects.githubusercontent.com"]);
  });

  it("only accepts lowercase slug pack names", () => {
    expect(isValidPackName("browser")).toBe(true);
    expect(isValidPackName("charts-2")).toBe(true);
    expect(isValidPackName("Browser")).toBe(false);
    expect(isValidPackName("../x")).toBe(false);
    expect(isValidPackName("")).toBe(false);
    expect(isValidPackName(42)).toBe(false);
  });
});

describe("pack archive URL", () => {
  const manifest = parsePackManifest(MANIFEST)!;

  it("pins the release to the app's own version", () => {
    expect(packArchiveUrl(manifest, manifest.packs[0])).toBe(
      "https://github.com/owner/repo/releases/download/v1.2.3/browser.zip",
    );
  });

  it("refuses a host outside the allowlist", () => {
    const evil = { ...manifest, allowedHosts: ["example.com"] };
    expect(packArchiveUrl(evil, evil.packs[0])).toBeNull();
  });

  it("returns null when the build recorded no archive", () => {
    expect(packArchiveUrl(manifest, { ...manifest.packs[0], zip: undefined })).toBeNull();
    expect(packArchiveUrl({ ...manifest, repository: "" }, manifest.packs[0])).toBeNull();
  });

  it("honours a mirror, but only over https or loopback http", () => {
    expect(
      packArchiveUrl(manifest, manifest.packs[0], "https://mirror.example.com/packs/"),
    ).toBe("https://mirror.example.com/packs/browser.zip");
    expect(
      packArchiveUrl(manifest, manifest.packs[0], "http://127.0.0.1:8080/packs"),
    ).toBe("http://127.0.0.1:8080/packs/browser.zip");
    expect(packArchiveUrl(manifest, manifest.packs[0], "http://example.com/packs")).toBeNull();
  });
});

describe("installed detection", () => {
  it("counts a pack installed only when every package directory exists", () => {
    const root = tempRoot();
    const site = sitePackagesDir(root);
    const pack = parsePackManifest(MANIFEST)!.packs[1]; // charts: plotly + matplotlib

    expect(isPackInstalled(root, pack)).toBe(false);

    fs.mkdirSync(path.join(site, "plotly"), { recursive: true });
    expect(isPackInstalled(root, pack)).toBe(false);

    fs.mkdirSync(path.join(site, "matplotlib"), { recursive: true });
    expect(isPackInstalled(root, pack)).toBe(true);
  });
});

describe("snapshot", () => {
  it("reports unsupported when the build has no manifest", () => {
    const root = tempRoot();
    const state = snapshot(root);
    expect(state.supported).toBe(false);
    expect(state.packs).toEqual([]);
    expect(state.reason).toMatch(/installed desktop app/i);
  });

  it("reports unsupported when there is no bundled Python runtime", () => {
    const root = tempRoot();
    fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
    fs.writeFileSync(manifestPath(root), JSON.stringify(MANIFEST));
    expect(readPackManifest(root)).not.toBeNull();
    expect(snapshot(root).supported).toBe(false);
  });

  it("lists every pack with an honest downloadable flag", () => {
    const root = tempRoot();
    fs.mkdirSync(sitePackagesDir(root), { recursive: true });
    fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
    fs.writeFileSync(manifestPath(root), JSON.stringify(MANIFEST));

    const state = snapshot(root);
    expect(state.supported).toBe(true);
    expect(state.version).toBe("1.2.3");
    expect(state.packs).toHaveLength(2);
    expect(state.packs.find((p) => p.name === "browser")?.downloadable).toBe(true);
    expect(state.packs.every((p) => p.installed === false)).toBe(true);
    expect(state.packs[0].label).toBe("Browser automation");
  });

  it("marks a pack without a digest as not downloadable", () => {
    const root = tempRoot();
    fs.mkdirSync(sitePackagesDir(root), { recursive: true });
    fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
    const noDigest = {
      ...MANIFEST,
      packs: MANIFEST.packs.map((p) => ({ ...p, sha256: undefined })),
    };
    fs.writeFileSync(manifestPath(root), JSON.stringify(noDigest));
    const packs = packStatuses(readPackManifest(root)!, root);
    expect(packs.every((p) => p.downloadable === false)).toBe(true);
    expect(packs[0].blockedReason).toBeTruthy();
  });
});

describe("appRoot", () => {
  it("can be pointed at an install directory", () => {
    process.env.BE_APP_ROOT = path.join(os.tmpdir(), "somewhere");
    expect(appRoot()).toBe(path.resolve(path.join(os.tmpdir(), "somewhere")));
  });
});

// ── end to end ──────────────────────────────────────────────────────────────
// The pipeline that actually matters: fetch from a URL, verify the digest,
// unpack, and land ONLY the manifest-named package directory. A mirror on
// loopback keeps it offline and deterministic.

function makePackZip(root: string, pkg = "fakepkg", body = "VALUE = 1\n") {
  const build = path.join(root, "build");
  const pkgDir = path.join(build, "site-packages", pkg);
  fs.mkdirSync(pkgDir, { recursive: true });
  fs.writeFileSync(path.join(pkgDir, "__init__.py"), body);
  const zipPath = path.join(root, `${pkg}.zip`);
  execFileSync("tar", ["-a", "-cf", zipPath, "-C", build, "."]);
  const bytes = fs.readFileSync(zipPath);
  return { bytes, sha256: crypto.createHash("sha256").update(bytes).digest("hex") };
}

async function serve(bytes: Buffer): Promise<{ url: string; close: () => Promise<void> }> {
  const server = http.createServer((_req, res) => {
    res.writeHead(200, { "content-type": "application/zip", "content-length": String(bytes.length) });
    res.end(bytes);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  return {
    url: `http://127.0.0.1:${port}/`,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

async function waitForJob(timeoutMs = 10_000) {
  const started = Date.now();
  for (;;) {
    const job = lastJob();
    if (job && (job.phase === "done" || job.phase === "error")) return job;
    if (Date.now() - started > timeoutMs) throw new Error("pack job timed out");
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

describe("install pipeline", () => {
  it("downloads, verifies the digest and installs the declared package", async () => {
    const root = tempRoot();
    const site = sitePackagesDir(root);
    fs.mkdirSync(site, { recursive: true });
    const { bytes, sha256 } = makePackZip(root);
    const mirror = await serve(bytes);

    try {
      process.env.BE_PACK_BASE_URL = mirror.url;
      fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
      fs.writeFileSync(
        manifestPath(root),
        JSON.stringify({
          schema: 1,
          version: "1.0.0",
          repository: "owner/repo",
          packs: [
            {
              name: "fakepkg",
              packages: ["fakepkg"],
              zip: "fakepkg.zip",
              zipBytes: bytes.length,
              sha256,
            },
          ],
        }),
      );

      expect(snapshot(root).packs[0].installed).toBe(false);
      startInstall("fakepkg", root);
      const job = await waitForJob();

      expect(job.phase).toBe("done");
      expect(fs.existsSync(path.join(site, "fakepkg", "__init__.py"))).toBe(true);
      expect(snapshot(root).packs[0].installed).toBe(true);
      // The staging copy must not outlive the install.
      expect(fs.existsSync(path.join(root, ".black-eclipse", "pack-staging", "fakepkg.zip"))).toBe(
        false,
      );
    } finally {
      await mirror.close();
    }
  });

  it("refuses a corrupt archive and installs nothing", async () => {
    const root = tempRoot();
    const site = sitePackagesDir(root);
    fs.mkdirSync(site, { recursive: true });
    const { bytes } = makePackZip(root, "badpkg", "BROKEN = 1\n");
    const mirror = await serve(bytes);

    try {
      process.env.BE_PACK_BASE_URL = mirror.url;
      fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
      fs.writeFileSync(
        manifestPath(root),
        JSON.stringify({
          schema: 1,
          version: "1.0.0",
          repository: "owner/repo",
          packs: [
            {
              name: "badpkg",
              packages: ["badpkg"],
              zip: "badpkg.zip",
              zipBytes: bytes.length,
              sha256: "0".repeat(64),
            },
          ],
        }),
      );

      startInstall("badpkg", root);
      const job = await waitForJob();

      expect(job.phase).toBe("error");
      expect(job.message).toMatch(/checksum/i);
      expect(fs.existsSync(path.join(site, "badpkg"))).toBe(false);
    } finally {
      await mirror.close();
    }
  });

  it("removes only the manifest-named package directories", () => {
    const root = tempRoot();
    const site = sitePackagesDir(root);
    fs.mkdirSync(path.join(site, "playwright"), { recursive: true });
    fs.mkdirSync(path.join(site, "keepme"), { recursive: true });
    fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
    fs.writeFileSync(manifestPath(root), JSON.stringify(MANIFEST));

    const after = removePack("browser", root);
    expect(fs.existsSync(path.join(site, "playwright"))).toBe(false);
    expect(fs.existsSync(path.join(site, "keepme"))).toBe(true);
    expect(after.find((p) => p.name === "browser")?.installed).toBe(false);
  });

  it("rejects an unknown pack and a traversal name", () => {    const root = tempRoot();
    fs.mkdirSync(sitePackagesDir(root), { recursive: true });
    fs.mkdirSync(path.dirname(manifestPath(root)), { recursive: true });
    fs.writeFileSync(manifestPath(root), JSON.stringify(MANIFEST));
    expect(() => startInstall("../evil", root)).toThrow(/Unknown pack/);
    expect(() => startInstall("not-in-manifest", root)).toThrow(/Unknown pack/);
  });
});
