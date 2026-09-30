import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
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

// ── line-ending guard (closeout Phase 2) ────────────────────────────────────
//
// WHY: with `core.autocrlf=true` and no `.gitattributes`, a one-line edit could
// show as a 700-line phantom diff (CRLF vs LF), breaking `git blame`. The root
// `.gitattributes` normalizes text to LF. This guard asks git's own attribute
// engine what it will do, so it fails if the normalization regresses.

function git(args: string[]): string {
  return execFileSync("git", args, { cwd: REPO_ROOT, encoding: "utf8" });
}

/** The `eol` git resolves for a path, via `git check-attr`. */
function eolFor(relPath: string): string {
  // Output: `<path>: eol: <value>`
  const out = git(["check-attr", "eol", "--", relPath]).trim();
  return out.split(":").pop()!.trim();
}

function isBinaryAttr(relPath: string): boolean {
  return git(["check-attr", "binary", "--", relPath]).includes("binary: set");
}

describe("line-ending normalization", () => {
  it("resolves LF for tracked text files (no phantom CRLF churn)", () => {
    for (const p of [
      "Black-Eclipse-site/docs/DECISIONS.md",
      "Black-Eclipse-site/skills/ARCHITECT.md",
      "Black-Eclipse-site/src/lib/api-guard.ts",
      "Black-Eclipse-site/python/harness/main.py",
      "AGENTS.md",
    ]) {
      expect(eolFor(p), `${p} should be eol=lf`).toBe("lf");
    }
  });

  it("marks the real binaries as binary so git never normalizes them", () => {
    expect(isBinaryAttr("Black-Eclipse-site/public/sounds/crisp/error.wav")).toBe(true);
    expect(isBinaryAttr("Black-Eclipse-site/src/app/favicon.ico")).toBe(true);
  });

  it("does not mark a text file as binary", () => {
    expect(isBinaryAttr("Black-Eclipse-site/src/lib/api-guard.ts")).toBe(false);
  });

  it("no tracked text file mixes CRLF and bare LF in the working tree", () => {
    // A tool appending CRLF to an LF-normalized file is what created the phantom
    // diffs. Any tracked text file containing BOTH a CRLF and a bare LF is a
    // regression. Binaries are skipped by extension (declared in .gitattributes)
    // rather than per-file `git check-attr`, which would be too slow at this scale.
    const BINARY_EXT = /\.(wav|ico|db|db-shm|db-wal|png|jpg|jpeg|gif|webp|woff2?|ttf|otf|pdf|zip|wasm|mp3|mp4)$/i;
    const tracked = git(["ls-files"]).split("\n").filter(Boolean);
    const mixed: string[] = [];
    for (const rel of tracked) {
      if (BINARY_EXT.test(rel)) continue;
      let bytes: Buffer;
      try {
        bytes = readFileSync(join(REPO_ROOT, rel));
      } catch {
        continue;
      }
      const hasCrlf = bytes.includes("\r\n");
      if (!hasCrlf) continue;
      let bareLf = false;
      for (let i = 0; i < bytes.length; i++) {
        if (bytes[i] === 0x0a && (i === 0 || bytes[i - 1] !== 0x0d)) {
          bareLf = true;
          break;
        }
      }
      if (bareLf) mixed.push(rel);
    }
    expect(mixed.slice(0, 20), `tracked text files mixing CRLF and bare LF: ${mixed.length} (${mixed.slice(0, 5).join(", ")})`).toEqual([]);
  });
});
