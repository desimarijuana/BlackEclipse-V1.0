// Phase 6.1 Milestone 1 — the view <-> draft <-> input round trip is
// field-complete. This is the front-door half of the "absent means preserve"
// contract: the UI always sends every field it owns, using explicit
// null/false/{}/[] to clear, so a save cannot silently reset a Phase-6 field.

import { describe, it, expect } from "vitest";
import {
  draftFromServer,
  draftToInput,
  emptyDraft,
  isShadowedByExclude,
  matchesGlob,
  resolveSelectedByGlobs,
  LIMIT_DEFAULTS,
} from "./mcp-draft";
import type { MCPServerView } from "./mcp-types";

/** A fully-populated runtime view: every field a user can meaningfully set. */
function fullView(): MCPServerView {
  return {
    id: "research",
    name: "Research Server",
    transport: "http",
    command: "",
    args: [],
    url: "https://mcp.example.test/mcp",
    auth: { kind: "header", name: "Authorization", prefix: "Bearer ", secretRef: "my_token" },
    env: { SCOPED_TOKEN: null },
    envKeys: ["SCOPED_TOKEN"],
    envAllowlist: ["HOME"],
    secretRefs: { API_TOKEN: "my_token" },
    secretRefNames: ["my_token"],
    secretCount: 1,
    cwd: "/work",
    enabled: true,
    trust: "untrusted",
    untrusted: true,
    selectedTools: { include: ["get_*"], exclude: ["get_secret"] },
    toolEffects: { get_quote: "read", put_order: "write" },
    acknowledgedEffectMismatches: ["API-post-search"],
    enabledEffects: ["read", "write"],
    dataSourceTools: { get_quote: "current_quote" },
    confirmedCatalogDigest: "abc123",
    lazy: true,
    keepaliveInterval: 60,
    idleTimeoutSeconds: 120,
    maxLifetimeSeconds: 600,
    sslVerify: "custom-ca",
    clientCertConfigured: true,
    capabilityToggles: { resources: true, prompts: true },
    resourceSchemes: ["note", "doc"],
    startupTimeoutMs: 5_000,
    catalogTimeoutMs: 7_000,
    callTimeoutMs: 9_000,
    outputLimitBytes: 50_000,
    maxConcurrency: 3,
    maxTools: 25,
    limits: { startupTimeoutMs: 5_000, maxTools: 25 },
    protocolVersion: "2025-11-25",
    description: "a full server",
    state: "connected",
    diagnostic: null,
    serverInfo: { name: "research", version: "1.0" },
    catalogDigest: "abc123",
    registeredTools: ["mcp__research__get_quote"],
    tools: [],
    capabilities: { resources: true },
    resources: [],
    prompts: [],
    lifecycle: { cachedTools: 0 },
  };
}

describe("draftFromServer / draftToInput round trip", () => {
  it("preserves the trust tier so a save cannot widen authority", () => {
    const input = draftToInput(draftFromServer(fullView())).server;
    expect(input.trust).toBe("untrusted");
  });

  it("preserves the include/exclude filter form", () => {
    const input = draftToInput(draftFromServer(fullView())).server;
    expect(input.selectedTools).toEqual({ include: ["get_*"], exclude: ["get_secret"] });
  });

  it("preserves tool effects and declared data sources", () => {
    const input = draftToInput(draftFromServer(fullView())).server;
    expect(input.toolEffects).toEqual({ get_quote: "read", put_order: "write" });
    expect(input.dataSourceTools).toEqual({ get_quote: "current_quote" });
  });

  it("preserves the acknowledged effect mismatches so a save cannot drop them", () => {
    const input = draftToInput(draftFromServer(fullView())).server;
    expect(input.acknowledgedEffectMismatches).toEqual(["API-post-search"]);
  });

  it("preserves capability toggles, lifecycle and TLS mode", () => {
    const input = draftToInput(draftFromServer(fullView())).server;
    expect(input.tools).toEqual({ resources: true, prompts: true });
    expect(input.resourceSchemes).toEqual(["note", "doc"]);
    expect(input.lazy).toBe(true);
    expect(input.keepaliveInterval).toBe(60);
    expect(input.idleTimeoutSeconds).toBe(120);
    expect(input.maxLifetimeSeconds).toBe(600);
    expect(input.sslVerify).toBeUndefined(); // custom-ca path not echoed; omitted = preserve
  });

  it("preserves enabled effects and the raw limits", () => {
    const input = draftToInput(draftFromServer(fullView())).server;
    expect(input.enabledEffects).toEqual(["read", "write"]);
    expect(input.startupTimeoutMs).toBe(5_000);
    expect(input.outputLimitBytes).toBe(50_000);
    expect(input.maxTools).toBe(25);
  });

  it("never echoes a stored client certificate value, but reports it configured", () => {
    const draft = draftFromServer(fullView());
    expect(draft.clientCertConfigured).toBe(true);
    expect(draft.clientCertText).toBe("");
    const input = draftToInput(draft).server;
    // Omitted (not null) so the runtime preserves the stored certificate.
    expect(input.clientCert).toBeUndefined();
    expect(input.clientKey).toBeUndefined();
  });

  it("sends explicit nulls/false/{}/[] to clear fields the operator emptied", () => {
    const draft = emptyDraft();
    draft.id = "x";
    draft.command = "python";
    draft.clearClientCert = true;
    const input = draftToInput(draft).server;
    expect(input.selectedTools).toEqual([]);
    expect(input.toolEffects).toEqual({});
    expect(input.acknowledgedEffectMismatches).toEqual([]);
    expect(input.dataSourceTools).toEqual({});
    expect(input.tools).toEqual({ resources: false, prompts: false });
    expect(input.lazy).toBe(false);
    expect(input.keepaliveInterval).toBeNull();
    expect(input.idleTimeoutSeconds).toBeNull();
    expect(input.maxLifetimeSeconds).toBeNull();
    expect(input.trust).toBe("full");
    expect(input.clientCert).toBeNull();
    expect(input.clientKey).toBeNull();
  });

  it("defaults omitted limits to the documented defaults", () => {
    const draft = emptyDraft();
    draft.id = "x";
    draft.command = "python";
    const input = draftToInput(draft).server;
    expect(input.startupTimeoutMs).toBe(LIMIT_DEFAULTS.startupTimeoutMs);
    expect(input.maxTools).toBe(LIMIT_DEFAULTS.maxTools);
  });

  it("uses oauth auth with no secret and sse transport for a remote server", () => {
    const view = fullView();
    view.transport = "sse";
    view.auth = { kind: "oauth" };
    view.url = "https://mcp.example.test/sse";
    const input = draftToInput(draftFromServer(view)).server;
    expect(input.transport).toBe("sse");
    expect(input.auth).toEqual({ kind: "oauth" });
  });

  it("preserves the catalog confirmation by omission (the editor does not own it)", () => {
    const input = draftToInput(draftFromServer(fullView())).server;
    expect("confirmedCatalogDigest" in input).toBe(false);
  });

  it("keeps a stored env key set without resending values", () => {
    const { server, envKeys } = draftToInput(draftFromServer(fullView()));
    expect(envKeys).toEqual(["SCOPED_TOKEN"]);
    expect(server.env).toEqual({});
  });
});

describe("glob selection helpers (exclude-mode honesty)", () => {
  it("matches fnmatch-style globs", () => {
    expect(matchesGlob("get_quote", "get_*")).toBe(true);
    expect(matchesGlob("put_order", "get_*")).toBe(false);
    expect(matchesGlob("a", "?")).toBe(true);
    expect(matchesGlob("ab", "?")).toBe(false);
  });

  it("mirrors the runtime rule: excluded beats included, empty include selects nothing", () => {
    expect(resolveSelectedByGlobs("get_quote", ["get_*"], [])).toBe(true);
    // Exclude only does not select (empty include selects nothing).
    expect(resolveSelectedByGlobs("get_quote", [], ["get_quote"])).toBe(false);
    // Exclude is applied after include: an excluded match is NOT selected.
    expect(resolveSelectedByGlobs("get_quote", ["get_*"], ["get_quote"])).toBe(false);
    expect(resolveSelectedByGlobs("get_secret", ["get_*"], ["*_secret"])).toBe(false);
  });

  it("reports a manually-selected tool the live filter would not select", () => {
    // The operator checked `put_order` by name, then set an include `get_*` that
    // does not match it: the live filter would drop it, so it is shadowed.
    expect(isShadowedByExclude("put_order", true, ["get_*"], [])).toBe(true);
    // A manual pick the globs DO select is not shadowed.
    expect(isShadowedByExclude("get_quote", true, ["get_*"], [])).toBe(false);
    // Not shadowed when the tool is not selected in the list.
    expect(isShadowedByExclude("put_order", false, ["get_*"], [])).toBe(false);
    // A manually-picked tool the exclude drops is shadowed.
    expect(isShadowedByExclude("get_secret", true, ["get_*"], ["*_secret"])).toBe(true);
  });
});
