import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  checkSecurityNetwork,
  decideSecurityApproval,
  getSecurityStatus,
  listSecurityApprovals,
  listSecurityCapabilities,
  revokeSecurityCapability,
  verifySecurityAudit,
} from "./security-browser";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("security-browser", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stays client-safe (no server imports)", () => {
    const source = readFileSync(join(__dirname, "security-browser.ts"), "utf8");
    expect(source).not.toMatch(/python-runtime|runtime-auth|child_process|node:fs/);
  });

  it("reads status from the proxy", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, profile: "secure", policyVersion: 3 }));
    const status = await getSecurityStatus();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/security/status");
    expect(status.profile).toBe("secure");
  });

  it("lists pending approvals and capabilities", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, approvals: [{ id: "a1" }] }));
    const approvals = await listSecurityApprovals();
    expect(approvals[0].id).toBe("a1");

    fetchMock.mockResolvedValue(jsonResponse({ success: true, capabilities: [{ id: "c1", active: true }] }));
    const caps = await listSecurityCapabilities();
    expect(caps[0].id).toBe("c1");
  });

  it("decides an approval via POST with the remember flag", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, approval: { id: "a1", status: "approved" } }));
    await decideSecurityApproval("a1", true, { remember: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/security/approvals/a1/decide");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ approve: true, remember: true });
  });

  it("revokes a capability and checks a URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true }));
    await revokeSecurityCapability("c1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/security/capabilities/c1/revoke");

    fetchMock.mockResolvedValue(jsonResponse({ success: true, decision: { decision: "deny" } }));
    const decision = await checkSecurityNetwork("http://169.254.169.254/");
    expect(decision.decision).toBe("deny");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/security/network/check");
  });

  it("surfaces a failed audit verification", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, valid: false, checked: 3 }));
    const result = await verifySecurityAudit();
    expect(result.valid).toBe(false);
  });
});
