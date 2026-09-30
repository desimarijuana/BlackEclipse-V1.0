import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

// Behavior guard for the .gitignore rules (Phase 2A / R4). It asserts what git
// actually ignores — not the text of the ignore files — so it cannot be fooled
// by a rule that reads correctly but matches nothing.

const APP_ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..");
const REPO_ROOT = join(APP_ROOT, "..");

function isIgnored(relPath: string): boolean {
  try {
    execFileSync("git", ["check-ignore", "-q", relPath], { cwd: REPO_ROOT });
    return true;
  } catch {
    return false;
  }
}

describe("gitignore behavior", () => {
  it("ignores the runtime databases and the local MCP secret store", () => {
    for (const p of [
      "Black-Eclipse-site/jdds.db",
      "Black-Eclipse-site/agent-memory.db",
      "Black-Eclipse-site/eclipse-memory.db",
      "Black-Eclipse-site/mcp-servers.json",
    ]) {
      expect(isIgnored(p), `${p} should be ignored`).toBe(true);
    }
  });

  it("does not silently ignore a path segment named `0`", () => {
    // The old root `.gitignore` began with the literal lines `0`, `0-shm`,
    // `0-wal`, which matched any path segment named `0`. A file must not vanish
    // because of a truncated wildcard.
    expect(isIgnored("Black-Eclipse-site/0")).toBe(false);
  });

  it("keeps the tracked skill files visible (an untracked path must not be ignored)", () => {
    // Guard against an over-broad rule hiding something real. `.opencode/skills`
    // is tracked; a sibling name must not be caught by a broad pattern.
    expect(isIgnored("Black-Eclipse-site/README.md")).toBe(false);
  });

  it("the jdds.db working file still exists on disk (untracked, not deleted)", () => {
    expect(existsSync(join(APP_ROOT, "jdds.db"))).toBe(true);
  });
});
