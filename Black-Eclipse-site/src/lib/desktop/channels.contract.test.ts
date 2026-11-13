import { describe, it, expect } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

// These are plain CommonJS build/launch modules (not part of the Next bundle).
const requireScript = createRequire(import.meta.url);
const channels = requireScript("../../../scripts/lib/channels.js") as {
  STABLE: { id: string; appPort: number; harnessPort: number; dataDir: string; buildDir: string };
  DEV: { id: string; appPort: number; harnessPort: number; dataDir: string; buildDir: string };
  channelFor: (raw?: string) => { id: string };
  channelEnv: (channel: unknown, opts?: { dataDir?: string; buildDir?: string }) => Record<string, string>;
};
const release = requireScript("../../../scripts/lib/desktop-release.js") as {
  buildLooksComplete: (dir: string) => boolean;
  readBuildId: (dir: string) => string | null;
  readPointer: (channel: unknown, name: string) => { buildId: string; valid: boolean } | null;
  writePointer: (channel: unknown, name: string, info: Record<string, unknown>) => void;
};

function fakeBuild(dir: string, buildId: string) {
  fs.mkdirSync(path.join(dir, "server", "app"), { recursive: true });
  fs.mkdirSync(path.join(dir, "static", buildId), { recursive: true });
  fs.writeFileSync(path.join(dir, "BUILD_ID"), buildId);
  fs.writeFileSync(path.join(dir, "routes-manifest.json"), JSON.stringify({ version: 3 }));
}

describe("desktop channel contract", () => {
  it("gives Stable and Dev disjoint ports and builds", () => {
    expect(channels.STABLE.appPort).not.toBe(channels.DEV.appPort);
    expect(channels.STABLE.harnessPort).not.toBe(channels.DEV.harnessPort);
    expect(channels.STABLE.buildDir).not.toBe(channels.DEV.buildDir);
    expect(channels.STABLE.dataDir).not.toBe(channels.DEV.dataDir);
  });

  it("maps an unknown channel to Stable", () => {
    expect(channels.channelFor("nonsense").id).toBe("stable");
    expect(channels.channelFor("dev").id).toBe("dev");
  });

  it("builds a consistent child environment per channel", () => {
    const env = channels.channelEnv(channels.DEV);
    expect(env.PORT).toBe(String(channels.DEV.appPort));
    expect(env.HARNESS_PY_PORT).toBe(String(channels.DEV.harnessPort));
    expect(env.HARNESS_PY_URL).toBe(`http://127.0.0.1:${channels.DEV.harnessPort}`);
    expect(env.HARNESS_CALLBACK_URL).toBe(`http://127.0.0.1:${channels.DEV.appPort}`);
    expect(env.NEXT_DIST_DIR).toBe(channels.DEV.buildDir);
    expect(env.BE_DATA_DIR).toBe(channels.DEV.dataDir);
  });

  it("recognises a complete build and rejects a partial one", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "be-channels-"));
    try {
      const good = path.join(root, "good");
      fakeBuild(good, "build-1");
      expect(release.readBuildId(good)).toBe("build-1");
      expect(release.buildLooksComplete(good)).toBe(true);

      const partial = path.join(root, "partial");
      fs.mkdirSync(path.join(partial, "server"), { recursive: true });
      fs.writeFileSync(path.join(partial, "BUILD_ID"), "build-2");
      expect(release.buildLooksComplete(partial)).toBe(false);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  });

  it("round-trips a release pointer and flags a missing target", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "be-pointers-"));
    try {
      const releasesDir = path.join(root, "releases");
      const channel = { ...channels.DEV, releasesDir };
      const dist = path.join(releasesDir, "build-a", ".next");
      fakeBuild(dist, "build-a");

      release.writePointer(channel, "current", { dir: dist, buildId: "build-a" });
      const current = release.readPointer(channel, "current");
      expect(current).not.toBeNull();
      expect(current?.buildId).toBe("build-a");
      expect(current?.valid).toBe(true);

      release.writePointer(channel, "previous", { dir: path.join(root, "gone"), buildId: "build-z" });
      expect(release.readPointer(channel, "previous")?.valid).toBe(false);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  });
});
