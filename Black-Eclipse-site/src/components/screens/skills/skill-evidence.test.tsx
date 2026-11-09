import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  SkillPromotionEvidencePanel,
  SkillVersionComparisonPanel,
} from "./skill-evidence";

describe("SkillVersionComparisonPanel", () => {
  it("offers every older version and a compare action", () => {
    const html = renderToStaticMarkup(
      <SkillVersionComparisonPanel
        skillId="finance.market-data"
        versions={["2.0.0", "1.1.0", "1.0.0"]}
        current="2.0.0"
      />,
    );
    expect(html).toContain("Compare");
    expect(html).toContain("v1.1.0");
    expect(html).toContain("v1.0.0");
    expect(html).not.toContain("only one version exists");
  });

  it("explains when there is nothing to compare", () => {
    const html = renderToStaticMarkup(
      <SkillVersionComparisonPanel skillId="solo" versions={["1.0.0"]} current="1.0.0" />,
    );
    expect(html).toContain("Only one version exists");
  });
});

describe("SkillPromotionEvidencePanel", () => {
  it("shows a loading state before the evidence arrives", () => {
    const html = renderToStaticMarkup(
      <SkillPromotionEvidencePanel skillId="finance.market-data" version="1.0.0" />,
    );
    expect(html).toContain("Loading promotion evidence");
  });
});
