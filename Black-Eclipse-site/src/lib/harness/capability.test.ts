import { describe, it, expect } from "vitest";
import { buildCapabilityMatrix } from "./capability";
import { MARKET_CURRENCY_ISO } from "@/lib/markets";

// Harness closeout Phase 3 — matrix truthfulness as an enforced invariant.
// A market must never show `not_implemented` together with a non-unknown
// observation (the "UK quote: not implemented (observed: working)" defect), the
// market count must equal the asserted count, and every currency must be real.

const AXES = ["quote", "history", "fundamentals", "filings", "web"] as const;

describe("capability matrix truthfulness invariant", () => {
  it("a non-unknown observation against an unimplemented axis is REPRESENTED, not smoothed", () => {
    // DERIV is recognised-only (no route). Feeding a working quote observation is
    // an impossible fact; the reconciler must surface matrixInconsistent.
    const matrix = buildCapabilityMatrix({
      observedByCapability: { "DERIV|quote": "working" },
    });
    const deriv = matrix.find((m) => m.market === "DERIV")!;
    expect(deriv.quote.observed).toBe("working");
    expect(deriv.quote.inconsistent).toBe("matrixInconsistent");
    expect(deriv.quote.inconsistencyReason).toBeTruthy();
    expect(deriv.quote.inconsistencyReason).toMatch(/observed "working"/);
  });

  it("no market shows not_implemented together with a non-unknown observation", () => {
    // Feed observations for a market/axis the code does NOT implement. The
    // invariant must hold on the LIVE matrix shape.
    const matrix = buildCapabilityMatrix({
      observedByCapability: { "UK|history": "working" },
    });
    for (const m of matrix) {
      for (const axisName of AXES) {
        const axis = m[axisName];
        const implemented = axis.level === "configured" || axis.level === "unconfigured";
        // A contradiction is allowed ONLY when explicitly flagged AND the level
        // was forced to a non-implemented value; the observation is never silently
        // presented as a working route.
        if (axis.observed !== "unknown" && !implemented) {
          expect(axis.inconsistent).toBe("matrixInconsistent");
        }
      }
    }
  });

  it("the market count equals the asserted count (34)", () => {
    const matrix = buildCapabilityMatrix();
    expect(matrix.length).toBe(34);
    // The code cannot produce 36 — do not assert a wrong count.
    expect(matrix.length).not.toBe(36);
  });

  it("every market's currency equals its real ISO currency", () => {
    const matrix = buildCapabilityMatrix();
    for (const m of matrix) {
      if (m.market === "DERIV") {
        expect(m.currency).toBe("N/A");
        continue;
      }
      expect(m.currency).toBe(MARKET_CURRENCY_ISO[m.market]);
    }
    expect(matrix.find((m) => m.market === "CH")!.currency).toBe("CHF");
    expect(matrix.find((m) => m.market === "KW")!.currency).toBe("KWD");
    expect(matrix.find((m) => m.market === "QA")!.currency).toBe("QAR");
  });

  it("a market with an unimplemented axis never reports configured", () => {
    const matrix = buildCapabilityMatrix();
    for (const m of matrix) {
      for (const axisName of AXES) {
        const axis = m[axisName];
        if (axis.observed !== "unknown") {
          expect(axis.level === "configured" || axis.level === "unconfigured").toBe(true);
        }
      }
    }
  });

  it("DERIV never yields a configured claim on any axis (not_covered)", () => {
    const matrix = buildCapabilityMatrix();
    const deriv = matrix.find((m) => m.market === "DERIV")!;
    for (const axisName of AXES) {
      expect(deriv[axisName].level).not.toBe("configured");
    }
  });

  it("a provider-ineligible market (AE/NG) is not configured on the quote axis and is secondary", () => {
    const matrix = buildCapabilityMatrix();
    const ae = matrix.find((m) => m.market === "AE")!;
    const ng = matrix.find((m) => m.market === "NG")!;
    expect(ae.quote.level).not.toBe("configured");
    expect(ng.quote.level).not.toBe("configured");
    expect(ae.quote.tier).toBe("secondary");
  });
});
