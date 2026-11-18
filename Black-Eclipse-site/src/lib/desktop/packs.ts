// ── Feature packs: download, verify, install ────────────────────────────────
//
// A packaged Black Eclipse ships the core only. Five Python capabilities
// (browser, ml, documents, computer, charts) live in optional packs because
// their wheels are large and most sessions never touch them.
//
// Before this module existed, a slim install simply lacked those packages with
// no way to obtain them — a feature would fail inside a lazily-imported
// function and the user had no action to take. That is the gap this closes.
//
// Trust model (same shape as the update channel):
//   * `config/packs.json` ships inside the app payload and is written at
//     package time by `scripts/desktop-package.js`.
//   * The archive URL is derived from that manifest, must be https, and must be
//     on an allowlisted host.
//   * Every archive is verified against the SHA-256 recorded at build time.
//     A mismatch deletes the download and installs nothing.
//   * Nothing is extracted outside a private staging directory; only package
//     directories NAMED IN THE MANIFEST are moved into site-packages. An
//     archive cannot invent a path.
//
// Everything here is server-only: it reads and writes the install directory.

import crypto from "node:crypto";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const USER_AGENT = "BlackEclipse-packs/1";

/** Human copy for every pack we know how to ship. Copy lives here, not in the
 *  manifest, so a manifest never has to carry marketing text. */
export const PACK_INFO: Record<
  string,
  { label: string; summary: string; unlocks: string[] }
> = {
  browser: {
    label: "Browser automation",
    summary: "Lets the agent open pages, fill forms and take screenshots in its own browser.",
    unlocks: ["Web research", "Form filling", "Page screenshots"],
  },
  ml: {
    label: "Local models",
    summary: "The numeric/ML stack used by local predictions, factors and backtests.",
    unlocks: ["Local predictions", "Factor models", "Quant experiments"],
  },
  documents: {
    label: "Document reading",
    summary: "Parses PDFs and office files so research uploads and filings become text.",
    unlocks: ["PDF extraction", "Uploads", "Filing search"],
  },
  computer: {
    label: "Desktop control",
    summary: "UI automation used when a task has to drive the desktop itself.",
    unlocks: ["Desktop actions", "Window control"],
  },
  charts: {
    label: "Advanced charting",
    summary: "Plotting stack used by generated charts that go beyond the built-in engine.",
    unlocks: ["Generated charts", "Plot exports"],
  },
};

export interface PackEntry {
  name: string;
  packages: string[];
  bytes?: number;
  zip?: string;
  zipBytes?: number;
  sha256?: string;
  target?: string;
}

export interface PackManifest {
  schema: number;
  version: string;
  repository: string;
  allowedHosts: string[];
  target?: string;
  packs: PackEntry[];
}

export type JobPhase = "downloading" | "verifying" | "installing" | "done" | "error";

export interface PackJob {
  pack: string;
  phase: JobPhase;
  received: number;
  total: number;
  message?: string;
  startedAt: string;
  finishedAt?: string;
}

export interface PackStatus {
  name: string;
  label: string;
  summary: string;
  unlocks: string[];
  packages: string[];
  /** Every package directory the manifest expects is present. */
  installed: boolean;
  /** Bytes the archive will download. */
  bytes: number;
  /** True when this build can fetch it (a download URL + digest exist). */
  downloadable: boolean;
  /** Why it cannot be fetched, when `downloadable` is false. */
  blockedReason?: string;
}

export interface PacksSnapshot {
  supported: boolean;
  reason?: string;
  version?: string;
  target?: string;
  packs: PackStatus[];
  active: PackJob | null;
  last: PackJob | null;
}

const PACK_NAME = /^[a-z0-9][a-z0-9-]{0,31}$/;

export function isValidPackName(value: unknown): value is string {
  return typeof value === "string" && PACK_NAME.test(value);
}

export function appRoot(): string {
  return process.env.BE_APP_ROOT ? path.resolve(process.env.BE_APP_ROOT) : process.cwd();
}

export function sitePackagesDir(root: string): string {
  return path.join(root, "scripts", "vendor", "python", "Lib", "site-packages");
}

export function manifestPath(root: string): string {
  return path.join(root, "config", "packs.json");
}

/**
 * Validate a manifest read from disk. Returns null (never throws) so a broken
 * manifest degrades to "no packs available" instead of breaking the route.
 */
export function parsePackManifest(raw: unknown): PackManifest | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Record<string, unknown>;
  if (!Array.isArray(value.packs)) return null;
  const packs: PackEntry[] = [];
  for (const item of value.packs) {
    if (!item || typeof item !== "object") continue;
    const pack = item as Record<string, unknown>;
    if (!isValidPackName(pack.name)) continue;
    const packages = Array.isArray(pack.packages)
      ? pack.packages.filter((p): p is string => typeof p === "string" && isValidPackName(p.toLowerCase()))
      : [];
    if (packages.length === 0) continue;
    packs.push({
      name: pack.name,
      packages,
      bytes: typeof pack.bytes === "number" ? pack.bytes : undefined,
      zip: typeof pack.zip === "string" ? pack.zip : undefined,
      zipBytes: typeof pack.zipBytes === "number" ? pack.zipBytes : undefined,
      sha256: typeof pack.sha256 === "string" ? pack.sha256.toLowerCase() : undefined,
      target: typeof pack.target === "string" ? pack.target : undefined,
    });
  }
  const allowedHosts = Array.isArray(value.allowedHosts)
    ? value.allowedHosts.filter((h): h is string => typeof h === "string").map((h) => h.toLowerCase())
    : ["github.com", "objects.githubusercontent.com"];
  return {
    schema: typeof value.schema === "number" ? value.schema : 1,
    version: typeof value.version === "string" ? value.version : "0.0.0",
    repository: typeof value.repository === "string" ? value.repository : "",
    allowedHosts,
    target: typeof value.target === "string" ? value.target : undefined,
    packs,
  };
}

export function readPackManifest(root: string): PackManifest | null {
  try {
    const raw = JSON.parse(fs.readFileSync(manifestPath(root), "utf8"));
    return parsePackManifest(raw);
  } catch {
    return null;
  }
}

/**
 * The archive URL for one pack. Pinned to the app's OWN version: a pack built
 * against 1.4.0 must not be installed into 1.5.0, because the wheels are
 * compiled per target and per release.
 *
 * `BE_PACK_BASE_URL` exists for mirrors and local testing. It still has to be
 * https (or plain http on loopback), so the env var cannot downgrade the
 * transport the recipe promises.
 */
export function packArchiveUrl(
  manifest: PackManifest,
  pack: PackEntry,
  overrideBase?: string,
): string | null {
  if (!pack.zip) return null;
  const zip = pack.zip.replace(/^\/+/, "");

  if (overrideBase) {
    try {
      const base = new URL(overrideBase);
      const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(base.hostname);
      if (base.protocol !== "https:" && !(base.protocol === "http:" && loopback)) return null;
      return new URL(zip, base.href.endsWith("/") ? base.href : `${base.href}/`).href;
    } catch {
      return null;
    }
  }

  if (!manifest.repository) return null;
  const pinned = manifest.version && manifest.version !== "0.0.0";
  const url = new URL(
    pinned
      ? `https://github.com/${manifest.repository}/releases/download/v${manifest.version}/${zip}`
      : `https://github.com/${manifest.repository}/releases/latest/download/${zip}`,
  );
  if (url.protocol !== "https:") return null;
  if (!manifest.allowedHosts.includes(url.hostname.toLowerCase())) return null;
  return url.href;
}

export function packBaseOverride(): string | undefined {
  const value = process.env.BE_PACK_BASE_URL?.trim();
  return value ? value : undefined;
}

/** True when every package directory the pack declares exists on disk. */
export function isPackInstalled(root: string, pack: PackEntry): boolean {
  const dir = sitePackagesDir(root);
  return pack.packages.every((pkg) => fs.existsSync(path.join(dir, pkg)));
}

export function packStatuses(manifest: PackManifest, root: string): PackStatus[] {
  return manifest.packs.map((pack) => {
    const info = PACK_INFO[pack.name] ?? {
      label: pack.name,
      summary: "Optional capability pack.",
      unlocks: [],
    };
    const url = packArchiveUrl(manifest, pack, packBaseOverride());
    const missingDigest = !pack.sha256;
    const downloadable = Boolean(url) && !missingDigest;
    return {
      name: pack.name,
      label: info.label,
      summary: info.summary,
      unlocks: info.unlocks,
      packages: pack.packages,
      installed: isPackInstalled(root, pack),
      bytes: pack.zipBytes ?? pack.bytes ?? 0,
      downloadable,
      blockedReason: downloadable
        ? undefined
        : "This build did not record a download for that pack — reinstall the app or use the offline edition.",
    };
  });
}

// ── job state ───────────────────────────────────────────────────────────────
// One job at a time, held in module memory. The window is a single process, so
// this is enough; a restart clears it and the UI re-reads installed state.

let active: PackJob | null = null;
let last: PackJob | null = null;

export function activeJob(): PackJob | null {
  return active;
}

export function lastJob(): PackJob | null {
  return last;
}

export function snapshot(root = appRoot()): PacksSnapshot {
  const manifest = readPackManifest(root);
  if (!manifest) {
    return {
      supported: false,
      reason:
        "This build has no feature-pack manifest. Feature packs are downloaded only in the installed desktop app.",
      packs: [],
      active,
      last,
    };
  }
  if (!fs.existsSync(sitePackagesDir(root))) {
    return {
      supported: false,
      reason:
        "This copy has no bundled Python runtime, so feature packs cannot be installed here. Use the installed desktop app.",
      packs: [],
      active,
      last,
    };
  }
  return {
    supported: true,
    version: manifest.version,
    target: manifest.target,
    packs: packStatuses(manifest, root),
    active,
    last,
  };
}

async function sha256File(file: string): Promise<string> {
  const hash = crypto.createHash("sha256");
  await pipeline(fs.createReadStream(file), hash);
  return hash.digest("hex");
}

async function downloadTo(url: string, dest: string, job: PackJob): Promise<void> {
  const res = await fetch(url, {
    redirect: "follow",
    headers: { "user-agent": USER_AGENT },
  });
  if (!res.ok || !res.body) {
    // A 404 here is not "no internet" — it means this release does not publish
    // that archive. Say so, and point at the edition that already has it.
    if (res.status === 404) {
      throw new Error(
        "This release does not publish that pack archive. Use the offline installer (BlackEclipse-Setup-<version>-full.exe), which includes every pack.",
      );
    }
    if (res.status === 403 || res.status >= 500) {
      throw new Error(
        `The download host refused the request (HTTP ${res.status}). Try again in a minute.`,
      );
    }
    throw new Error(`Download failed (HTTP ${res.status}). Check your connection.`);
  }
  const declared = Number(res.headers.get("content-length") ?? 0);
  if (Number.isFinite(declared) && declared > 0) job.total = declared;

  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const out = fs.createWriteStream(dest);
  const body = Readable.fromWeb(res.body as Parameters<typeof Readable.fromWeb>[0]);
  body.on("data", (chunk: Buffer) => {
    job.received += chunk.length;
  });
  await pipeline(body, out);
}

function tarBinary(): string {
  if (process.platform !== "win32") return "tar";
  const system32 = path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "tar.exe");
  return fs.existsSync(system32) ? system32 : "tar";
}

/**
 * Start installing a pack. Resolves immediately with the job; poll
 * `snapshot()`/`activeJob()` for progress. Failures land in `last` with a
 * plain-English message, never as a silent no-op.
 */
export function startInstall(name: unknown, root = appRoot()): PackJob {
  if (!isValidPackName(name)) {
    throw Object.assign(new Error("Unknown pack"), { status: 400 });
  }
  if (active) {
    throw Object.assign(new Error(`Already installing "${active.pack}".`), { status: 409 });
  }
  const manifest = readPackManifest(root);
  if (!manifest) {
    throw Object.assign(
      new Error("This build has no feature-pack manifest, so nothing can be downloaded."),
      { status: 400 },
    );
  }
  const pack = manifest.packs.find((p) => p.name === name);
  if (!pack) {
    throw Object.assign(new Error(`Unknown pack "${name}"`), { status: 404 });
  }
  if (isPackInstalled(root, pack)) {
    throw Object.assign(new Error(`${name} is already installed.`), { status: 409 });
  }
  const url = packArchiveUrl(manifest, pack, packBaseOverride());
  if (!url || !pack.sha256) {
    throw Object.assign(
      new Error(
        "This build did not record a download for that pack. Use the offline installer, which includes every pack.",
      ),
      { status: 400 },
    );
  }

  const job: PackJob = {
    pack: pack.name,
    phase: "downloading",
    received: 0,
    total: pack.zipBytes ?? 0,
    startedAt: new Date().toISOString(),
  };
  active = job;
  last = null;

  void runInstall(pack, url, pack.sha256, job, root).catch(() => {
    /* runInstall already recorded the failure */
  });

  return job;
}

async function runInstall(
  pack: PackEntry,
  url: string,
  digest: string,
  job: PackJob,
  root: string,
): Promise<void> {
  const stagingRoot = path.join(root, ".black-eclipse", "pack-staging");
  const zipPath = path.join(stagingRoot, `${pack.name}.zip`);
  const extractDir = path.join(stagingRoot, `${pack.name}-extract`);

  try {
    fs.mkdirSync(stagingRoot, { recursive: true });
    fs.rmSync(extractDir, { recursive: true, force: true });

    await downloadTo(url, zipPath, job);

    job.phase = "verifying";
    const actual = await sha256File(zipPath);
    if (actual !== digest) {
      throw new Error(
        "The downloaded pack did not match its published checksum, so nothing was installed. Try again.",
      );
    }

    job.phase = "installing";
    fs.mkdirSync(extractDir, { recursive: true });
    try {
      await execFileAsync(tarBinary(), ["-xf", zipPath, "-C", extractDir], {
        windowsHide: true,
        maxBuffer: 1024 * 1024 * 8,
      });
    } catch (err) {
      throw new Error(
        `Could not unpack the pack archive: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    const extractedSite = path.join(extractDir, "site-packages");
    const targetSite = sitePackagesDir(root);
    for (const pkg of pack.packages) {
      const from = path.join(extractedSite, pkg);
      if (!fs.existsSync(from)) {
        throw new Error(`The pack archive did not contain "${pkg}". Nothing was installed.`);
      }
      const to = path.join(targetSite, pkg);
      fs.rmSync(to, { recursive: true, force: true });
      // Same volume (both under the install root), so a rename is instant and
      // never walks deep wheel paths that can exceed MAX_PATH on Windows. The
      // copy is the fallback for a staging dir that somehow landed elsewhere.
      try {
        fs.renameSync(from, to);
      } catch {
        fs.cpSync(from, to, { recursive: true });
      }
    }

    job.phase = "done";
    job.message = `${pack.name} installed.`;
    job.finishedAt = new Date().toISOString();
  } catch (err) {
    job.phase = "error";
    job.message = err instanceof Error ? err.message : String(err);
    job.finishedAt = new Date().toISOString();
  } finally {
    try {
      fs.rmSync(zipPath, { force: true });
      fs.rmSync(extractDir, { recursive: true, force: true });
    } catch {}
    active = null;
    last = { ...job };
  }
}

/** Remove an installed pack. Only directories named in the manifest are touched. */
export function removePack(name: unknown, root = appRoot()): PackStatus[] {
  if (!isValidPackName(name)) {
    throw Object.assign(new Error("Unknown pack"), { status: 400 });
  }
  const manifest = readPackManifest(root);
  if (!manifest) {
    throw Object.assign(new Error("This build has no feature-pack manifest."), { status: 400 });
  }
  const pack = manifest.packs.find((p) => p.name === name);
  if (!pack) {
    throw Object.assign(new Error(`Unknown pack "${name}"`), { status: 404 });
  }
  if (active) {
    throw Object.assign(new Error("An install is running. Try again when it finishes."), { status: 409 });
  }
  const dir = sitePackagesDir(root);
  for (const pkg of pack.packages) {
    fs.rmSync(path.join(dir, pkg), { recursive: true, force: true });
  }
  return packStatuses(manifest, root);
}
