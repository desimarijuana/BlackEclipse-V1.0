import { describe, it, expect } from "vitest";
import { GitError } from "./service";

// The Git ENGINE lives in the Python runtime (`python/harness/git/`); this TS
// module is a thin proxy. There is no TS git logic left to unit-test — the
// engine's own behaviour is covered by the Python suite. We assert only the wire
// error type the front door throws.

describe("GitError", () => {
  it("carries a machine-readable code", () => {
    const err = new GitError("SECRET_DETECTED", "nope");
    expect(err.code).toBe("SECRET_DETECTED");
    expect(err).toBeInstanceOf(Error);
  });
});
