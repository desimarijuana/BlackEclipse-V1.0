import { describe, it, expect } from "vitest";
import { findSecretPaths, GitError } from "./service";

// The git service's safety rails are pure functions we can test without a repo.
// The command runners are integration-tested against the live API.

describe("findSecretPaths", () => {
  it("flags .env, keys, databases and credential files", () => {
    const flagged = findSecretPaths([
      "Black-Eclipse-site/.env",
      "Black-Eclipse-site/.env.local",
      "certs/server.pem",
      "certs/server.key",
      "deploy/keystore.p12",
      "jdds.db",
      "agent-memory.db-wal",
      "config/credentials.json",
      ".connector-key",
      "secrets.yaml",
      "id_rsa",
    ]);
    expect(flagged.length).toBe(11);
  });

  it("does NOT flag ordinary source and doc files", () => {
    const clean = findSecretPaths([
      "src/lib/harness/graph.py",
      "docs/harness/phase-2-progress.md",
      "package.json",
      "environment.ts",
      "src/lib/keyboard.ts",
      "mydb.sqlite.test.ts",
    ]);
    expect(clean).toEqual([]);
  });

  it("flags a .db but not a filename that merely mentions db", () => {
    expect(findSecretPaths(["data/jdds.db"])).toEqual(["data/jdds.db"]);
    expect(findSecretPaths(["src/lib/db.ts"])).toEqual([]);
  });
});

describe("GitError", () => {
  it("carries a machine-readable code", () => {
    const err = new GitError("SECRET_BLOCKED", "nope");
    expect(err.code).toBe("SECRET_BLOCKED");
    expect(err).toBeInstanceOf(Error);
  });
});
