import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { isOperatorRequest } from "./skills-client";
import { clientIsOperator } from "./skills-browser";

// The skill front door's authorization rule must match the repo's existing
// mutation guard exactly: same-origin browser, runtime secret, or loopback.
// These tests pin that contract so a change to the guard can't silently either
// lock out the zero-config local install or open a public deployment.

const SECRET = "a-very-secret-value";

function makeRequest(headers: Record<string, string>, url = "http://localhost:3000/api/skills/x/enable") {
  return new Request(url, { method: "POST", headers });
}

describe("isOperatorRequest", () => {
  const original = process.env.CRON_SECRET;

  beforeEach(() => {
    delete process.env.CRON_SECRET;
  });

  afterEach(() => {
    if (original === undefined) delete process.env.CRON_SECRET;
    else process.env.CRON_SECRET = original;
  });

  it("allows a same-origin browser request (local zero-config install)", () => {
    const req = makeRequest({ origin: "http://localhost:3000" });
    expect(isOperatorRequest(req)).toBe(true);
  });

  it("rejects a cross-origin request without a secret", () => {
    const req = makeRequest({ origin: "http://evil.example.com" });
    expect(isOperatorRequest(req)).toBe(false);
  });

  it("rejects a no-origin request to a public host without a secret", () => {
    const req = makeRequest({}, "https://app.example.com/api/skills/x/enable");
    expect(isOperatorRequest(req)).toBe(false);
  });

  it("allows a loopback request with no origin", () => {
    const req = makeRequest({}, "http://127.0.0.1:3000/api/skills/x/enable");
    expect(isOperatorRequest(req)).toBe(true);
  });

  it("allows a caller presenting the runtime secret", () => {
    process.env.CRON_SECRET = SECRET;
    const req = makeRequest(
      { authorization: `Bearer ${SECRET}` },
      "https://app.example.com/api/skills/x/enable"
    );
    expect(isOperatorRequest(req)).toBe(true);
  });

  it("rejects a wrong secret on a public host", () => {
    process.env.CRON_SECRET = SECRET;
    const req = makeRequest(
      { authorization: "Bearer nope" },
      "https://app.example.com/api/skills/x/enable"
    );
    expect(isOperatorRequest(req)).toBe(false);
  });

  it("treats the placeholder secret as unset", () => {
    process.env.CRON_SECRET = "change-me-to-a-random-secret";
    const req = makeRequest(
      { authorization: "Bearer change-me-to-a-random-secret" },
      "https://app.example.com/api/skills/x/enable"
    );
    // Falls through to the local/cross-origin rules → not operator.
    expect(isOperatorRequest(req)).toBe(false);
  });

  it("returns false for no request", () => {
    expect(isOperatorRequest(undefined)).toBe(false);
  });
});

describe("clientIsOperator", () => {
  it("is false outside a browser (SSR-safe presentation hint)", () => {
    // The vitest environment is `node`, so no `window` exists. In the browser
    // this returns true; it only decides whether the UI renders operator
    // controls — the server re-checks every action.
    expect(clientIsOperator()).toBe(false);
  });
});
