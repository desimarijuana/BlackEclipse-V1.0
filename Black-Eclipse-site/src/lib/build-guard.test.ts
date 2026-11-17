import { describe, expect, it } from "vitest";
import path from "node:path";

// The build guard is policy, not plumbing: it decides whether a plain
// `npm run build` may rewrite `.next` while a desktop channel is live. It lives
// in scripts/ because that is where the build entry point is, so it is loaded
// directly rather than imported through the Next alias map.
type Guard = {
  allowBuildWhileRunning: (raw: string | undefined) => boolean;
  shouldRefuseBuild: (input?: { live?: Array<Record<string, unknown>>; allow?: boolean }) => boolean;
  describeLive: (live: Array<Record<string, unknown>>) => string;
  refusalMessage: (live: Array<Record<string, unknown>>) => string;
};

// The guard is a plain CommonJS script shared with the build tooling; a static
// import cannot target a path resolved at runtime.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const guard = require(path.resolve(process.cwd(), "scripts/lib/build-guard.js")) as Guard;

const STABLE_LIVE = [{ id: "stable", label: "Stable", appPort: 3100, pid: 1234 }];

describe("allowBuildWhileRunning", () => {
  it("accepts the documented truthy spellings", () => {
    for (const raw of ["1", "true", "yes", "on", " ON "]) {
      expect(guard.allowBuildWhileRunning(raw)).toBe(true);
    }
  });

  it("treats everything else as not allowed", () => {
    for (const raw of [undefined, "", "0", "false", "no", "off", "nope"]) {
      expect(guard.allowBuildWhileRunning(raw)).toBe(false);
    }
  });
});

describe("shouldRefuseBuild", () => {
  it("refuses when a channel is live and the escape hatch is not set", () => {
    expect(guard.shouldRefuseBuild({ live: STABLE_LIVE, allow: false })).toBe(true);
  });

  it("allows the managed paths that own the pin and restart", () => {
    expect(guard.shouldRefuseBuild({ live: STABLE_LIVE, allow: true })).toBe(false);
  });

  it("allows a normal build when nothing is running", () => {
    expect(guard.shouldRefuseBuild({ live: [], allow: false })).toBe(false);
  });

  it("never throws on missing input", () => {
    expect(guard.shouldRefuseBuild({})).toBe(false);
    expect(guard.shouldRefuseBuild()).toBe(false);
  });
});

describe("refusalMessage", () => {
  it("names the live channel, its port and pid", () => {
    const text = guard.refusalMessage(STABLE_LIVE);
    expect(text).toContain("Stable");
    expect(text).toContain("3100");
    expect(text).toContain("1234");
  });

  it("falls back to the window pid when the server is between restarts", () => {
    const text = guard.refusalMessage([
      { id: "stable", label: "Stable", appPort: 3100, windowPids: [42] },
    ]);
    expect(text).toContain("Stable");
    expect(text).toContain("window pid 42");
  });

  it("points at the managed commands, not just 'do not do that'", () => {
    const text = guard.refusalMessage(STABLE_LIVE);
    expect(text).toContain("npm run desktop:refresh");
    expect(text).toContain("black stop");
    expect(text).toContain("npm run desktop:dev");
  });

  it("stays sensible with no live channel detail", () => {
    expect(guard.refusalMessage([])).toContain("refusing to rebuild");
  });
});
