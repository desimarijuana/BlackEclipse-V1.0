import { describe, expect, it } from "vitest";
import { pickServableModel } from "./use-chat-model";

// The default-model reconciliation: a keyless local provider's declared default
// can be a placeholder the server does not serve (`llama3.1` on a box with only
// cloud models), which makes every Ask AI / Analyze run fail with a raw 404.
// These lock the rule that the default only changes to a model known to be
// served, and a user's explicit choice is never overridden.

describe("pickServableModel", () => {
  it("adopts the first served model when the current one is not served", () => {
    expect(
      pickServableModel(["deepseek-v4.1-flash:cloud", "glm-5.3:cloud"], "llama3.1"),
    ).toBe("deepseek-v4.1-flash:cloud");
  });

  it("keeps a current model that is already served (an explicit choice stands)", () => {
    expect(pickServableModel(["llama3.1", "deepseek-v4.1-flash:cloud"], "llama3.1")).toBeNull();
  });

  it("does nothing when nothing is known to be served", () => {
    expect(pickServableModel([], "llama3.1")).toBeNull();
  });

  it("ignores empty/garbage entries", () => {
    expect(pickServableModel(["", "glm-5.3:cloud"], "llama3.1")).toBe("glm-5.3:cloud");
    expect(pickServableModel(["", ""], "llama3.1")).toBeNull();
  });

  it("adopts a served model even when nothing is currently selected", () => {
    expect(pickServableModel(["deepseek-v4.1-flash:cloud"], "")).toBe("deepseek-v4.1-flash:cloud");
  });
});
