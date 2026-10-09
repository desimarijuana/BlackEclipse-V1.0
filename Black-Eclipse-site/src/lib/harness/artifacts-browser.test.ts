import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { listArtifacts, getArtifact, downloadUrl, thumbnailUrl, bulkAction } from "./artifacts-browser";

describe("artifacts-browser", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stays client-safe (no server imports)", () => {
    const source = readFileSync(join(__dirname, "artifacts-browser.ts"), "utf8");
    expect(source).not.toMatch(/python-runtime|runtime-auth|child_process|node:fs/);
  });

  it("builds a filtered, paginated list request and maps the page", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          artifacts: [{ id: "a1", name: "r.csv" }],
          total: 1,
          limit: 24,
          offset: 0,
          hasMore: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const page = await listArtifacts({ q: "r", category: "dataset", tags: ["x", "y"], limit: 24 });
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/artifacts?");
    expect(url).toContain("q=r");
    expect(url).toContain("category=dataset");
    expect(url).toContain("tags=x");
    expect(url).toContain("tags=y");
    expect(page.total).toBe(1);
    expect(page.artifacts[0].id).toBe("a1");
  });

  it("surfaces the server error message verbatim", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "ARTIFACT_NOT_FOUND", message: "artifact not found" } }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    );
    await expect(getArtifact("missing")).rejects.toThrow("artifact not found");
  });

  it("builds same-origin download and thumbnail URLs", () => {
    expect(downloadUrl("a1")).toBe("/api/artifacts/a1/download");
    expect(downloadUrl("a1", 2)).toBe("/api/artifacts/a1/download?version=2");
    expect(thumbnailUrl("a1")).toBe("/api/artifacts/a1/thumbnail");
  });

  it("posts bulk actions to the proxy", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ success: true, succeeded: ["a1"], failed: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const result = await bulkAction(["a1"], "archive");
    expect(result.succeeded).toEqual(["a1"]);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ artifactIds: ["a1"], action: "archive" });
  });
});
