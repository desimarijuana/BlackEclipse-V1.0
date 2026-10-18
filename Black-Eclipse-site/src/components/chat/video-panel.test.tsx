// ── VideoPanel SSR tests ─────────────────────────────────────────────────────
// The vitest environment is `node` (no @testing-library/jsdom), so — like the
// canvas and response-render tests — this renders the real component with
// `react-dom/server`. The polling/action logic is exercised through the pure
// coercers in `video-view.test.ts`; here we pin what the markup shows for an
// absent blob, a queued render, and a collected preview job.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { VideoPanel } from "./video-panel";

function render(video: unknown): string {
  return renderToStaticMarkup(<VideoPanel video={video} />);
}

describe("VideoPanel", () => {
  it("renders nothing without a blob", () => {
    expect(render(undefined)).toBe("");
    expect(render({ jobs: [] })).toBe("");
  });

  it("shows a queued render with an honest status and a cancel control", () => {
    const html = render({
      type: "video",
      status: "collected",
      jobs: [
        {
          jobId: "job_1",
          projectId: "vprj_a",
          projectName: "BTC recap",
          kind: "render",
          mode: "final",
        },
      ],
    });
    expect(html).toContain("Video");
    expect(html).toContain("Final render");
    expect(html).toContain("BTC recap");
    expect(html).toContain("QUEUED");
    expect(html).toContain("Cancel");
    // No player and no download before the job actually succeeds.
    expect(html).not.toContain("<video");
    expect(html).not.toContain("Download");
  });

  it("labels a preview job without calling it a video", () => {
    const html = render({
      type: "video",
      jobs: [
        { jobId: "job_2", projectId: "vprj_a", projectName: "Look", kind: "preview" },
      ],
    });
    expect(html).toContain("Preview");
    expect(html).not.toContain("<video");
  });
});
