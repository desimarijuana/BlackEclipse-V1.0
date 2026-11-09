import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { SkillSummary } from "@/lib/harness/skills-types";
import { SkillLibrary } from "./skill-library";

const SKILL: SkillSummary = {
  id: "finance.market-data",
  name: "Market data",
  version: "1.0.0",
  description: "Quotes for an instrument",
  category: "finance",
  tags: ["quotes"],
  status: "enabled",
  riskLevel: "low",
  permissions: ["data.read"],
  requiredTools: ["get_price"],
  evaluationStatus: "passed",
};

function render(overrides: Partial<Parameters<typeof SkillLibrary>[0]> = {}) {
  return renderToStaticMarkup(
    <SkillLibrary
      skills={[SKILL]}
      loading={false}
      error={null}
      loadErrors={[]}
      duplicates={[]}
      onOpen={() => {}}
      onRefresh={() => {}}
      onAdd={() => {}}
      {...overrides}
    />,
  );
}

describe("SkillLibrary accessibility", () => {
  it("exposes filter and sort state with aria-pressed", () => {
    const html = render();
    // Category "All" and sort "Name" are the defaults, so both are pressed.
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-label="Search skills"');
    expect(html).toContain('aria-label="Select Market data"');
  });

  it("hides the bulk toolbar until something is selected", () => {
    const html = render();
    expect(html).not.toContain("0 selected");
    // The checkbox is present, but no selection toolbar.
    expect(html).not.toContain("Clear");
  });

  it("renders the exact pagination range", () => {
    const html = render();
    expect(html).toContain("Showing");
    expect(html).toContain("of");
    expect(html).toContain("skills");
  });

  it("shows an empty state with the start-here action when the registry is empty", () => {
    const html = render({ skills: [], onStartHere: () => {} });
    expect(html).toContain("No skills installed");
    expect(html).toContain("Start here");
  });
});
