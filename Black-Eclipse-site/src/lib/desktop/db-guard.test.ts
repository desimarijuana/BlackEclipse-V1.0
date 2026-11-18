// The database guard is the only code allowed to rebuild a user's database, so
// pin the one outcome that is destructive when wrong: a guard that cannot load
// its SQLite binding must report an environment problem (exit 2) and leave the
// file alone — never call it corruption (exit 1) and replace the user's data.
//
// This is how a release with no native binding bricked first launch: the guard
// exited 1, the server stored that failure, and every later launch refused.
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const GUARD = fileURLToPath(new URL("../../../scripts/db-guard.js", import.meta.url));

describe("db-guard", () => {
  it("reports a missing SQLite binding as an environment problem, not corruption", () => {
    // A copy outside the checkout has no node_modules/better-sqlite3 to resolve.
    const lonely = mkdtempSync(join(tmpdir(), "be-guard-"));
    mkdirSync(join(lonely, "scripts"), { recursive: true });
    copyFileSync(GUARD, join(lonely, "scripts", "db-guard.js"));

    const result = spawnSync(process.execPath, [join(lonely, "scripts", "db-guard.js"), "check"], {
      env: { ...process.env, BE_DATA_DIR: lonely },
      encoding: "utf8",
    });

    expect(result.stderr).toContain("better-sqlite3 not found");
    expect(result.status).toBe(2);
  });
});
