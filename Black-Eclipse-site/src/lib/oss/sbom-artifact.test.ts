import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

// Vitest runs from Black-Eclipse-site/, so the public artifacts live one level up.
const appRoot = process.cwd();
const repoRoot = path.resolve(appRoot, "..");
const sbomPath = path.join(repoRoot, "sbom.cdx.json");
const noticesPath = path.join(repoRoot, "THIRD-PARTY-NOTICES.md");

describe("public SBOM artifact", () => {
  it("is current with the lockfiles", () => {
    // The generator compares the committed pair against package-lock.json and
    // python/requirements.lock; --check is the same mode CI runs.
    expect(() =>
      execFileSync(
        process.execPath,
        [path.join(appRoot, "scripts", "generate-sbom.js"), "--check"],
        { cwd: appRoot, stdio: "pipe" }
      )
    ).not.toThrow();
  });

  it("is valid CycloneDX 1.5 with unique component references", () => {
    const bom = JSON.parse(fs.readFileSync(sbomPath, "utf8"));
    const pkg = JSON.parse(fs.readFileSync(path.join(appRoot, "package.json"), "utf8"));

    expect(bom.bomFormat).toBe("CycloneDX");
    expect(bom.specVersion).toBe("1.5");
    expect(bom.metadata.component.name).toBe("black-eclipse");
    expect(bom.metadata.component.version).toBe(pkg.version);

    // A dedupe regression previously produced 23 duplicate bom-refs. CycloneDX
    // identifies a component by that reference, so uniqueness is contractual.
    expect(bom.components.length).toBeGreaterThan(1000);
    const refs = new Set(bom.components.map((component: { "bom-ref": string }) => component["bom-ref"]));
    expect(refs.size).toBe(bom.components.length);

    for (const component of bom.components) {
      expect(component.type).toBe("library");
      expect(component.name).toBeTruthy();
      expect(component.version).toBeTruthy();
      expect(component.purl).toMatch(/^pkg:(npm|pypi)\//);
      expect(component.licenses?.[0]).toBeTruthy();
    }
  });

  it("notices match the component count and keep the licence carve-out", () => {
    const bom = JSON.parse(fs.readFileSync(sbomPath, "utf8"));
    const text = fs.readFileSync(noticesPath, "utf8");

    expect(text).toContain(`Components: **${bom.components.length}**`);
    expect(text).toContain("AGPL-3.0-only");
    // Python packages declare no licence in the lockfile; the file says so
    // rather than guessing, and that caveat is part of the contract.
    expect(text).toContain("NOASSERTION");
  });
});
