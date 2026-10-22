// The release gate is ONE gate: the local `check:all` and the repository
// workflow must run the same checks, including the corpus gate. A future edit
// that silently drops a step is a regression, so the wiring is pinned here.

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(__dirname, "..", "..", "..");
const workflow = readFileSync(join(root, ".github", "workflows", "ci.yml"), "utf8");
const checkAll = readFileSync(
  join(root, "Black-Eclipse-site", "scripts", "check-all.js"),
  "utf8",
);

describe("the release gate is wired in CI and locally", () => {
  it("the repository workflow runs the unit, python and eval gates", () => {
    expect(workflow).toContain("npm test");
    expect(workflow).toContain("npm run test:evals");
    expect(workflow).toContain("npx tsc --noEmit");
  });

  it("both the workflow and the local gate run the corpus gate", () => {
    expect(workflow).toContain("scripts/rsl-nightly.js");
    expect(workflow).toContain(
      "python/harness/evaluation/baselines/corpus_v1.json",
    );
    expect(checkAll).toContain("scripts/rsl-nightly.js");
    expect(checkAll).toContain(
      "python/harness/evaluation/baselines/corpus_v1.json",
    );
  });
});
