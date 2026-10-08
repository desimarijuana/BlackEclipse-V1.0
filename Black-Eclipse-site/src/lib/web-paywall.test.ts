import { describe, expect, it } from "vitest";
import { detectPaywall } from "@/lib/web-paywall";

// A paywall/login wall is not evidence and not a generic failure. These tests
// pin the deterministic detection so the transport can emit `paywalled` and the
// research layer can escalate to a credentialed browser session.

describe("detectPaywall", () => {
  it("flags an explicit subscription wall", () => {
    const r = detectPaywall({ text: "Subscribe to continue reading this article." });
    expect(r.paywalled).toBe(true);
    expect(r.loginGated).toBe(false);
  });

  it("flags a metered paywall", () => {
    expect(detectPaywall({ text: "You have reached your free article limit." }).paywalled).toBe(true);
  });

  it("flags a login wall as login-gated", () => {
    const r = detectPaywall({ text: "Please sign in to your account to view this story." });
    expect(r.paywalled).toBe(true);
    expect(r.loginGated).toBe(true);
  });

  it("flags a 402 Payment Required even with no text", () => {
    const r = detectPaywall({ text: "", httpStatus: 402 });
    expect(r.paywalled).toBe(true);
    expect(r.loginGated).toBe(false);
  });

  it("does NOT treat a bare 403 with no body as a paywall (bot/geo block)", () => {
    expect(detectPaywall({ text: "", httpStatus: 403 }).paywalled).toBe(false);
  });

  it("flags a short soft-walled body", () => {
    expect(detectPaywall({ text: "Log in or subscribe for unlimited access." }).paywalled).toBe(true);
  });

  it("does NOT flag a long article that merely mentions 'sign in'", () => {
    const longBody = "The market rallied today. ".repeat(200) + " Readers can sign in to comment on this piece.";
    expect(detectPaywall({ text: longBody }).paywalled).toBe(false);
  });

  it("does NOT flag an ordinary article", () => {
    expect(detectPaywall({ text: "NVIDIA reported record revenue for the quarter." }).paywalled).toBe(false);
  });

  it("reads the HTML when no extracted text is available", () => {
    expect(detectPaywall({ html: "<div>Subscribe to continue</div>" }).paywalled).toBe(true);
  });
});
