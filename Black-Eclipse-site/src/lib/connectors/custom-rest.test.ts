import { describe, it, expect } from "vitest";
import crypto from "node:crypto";
import { buildCustomRestConnector, buildRequestUrl, findUndeclaredPlaceholders, joinPaths, validateHeaders } from "./custom-rest";
import type { CustomConnectorConfig, ConnectorTransport } from "./custom-rest";
import { encryptSecret, decryptSecret } from "./secrets";
import { OutboundError } from "./security";

const KEY = crypto.randomBytes(32);
const decrypt = (payload: string) => decryptSecret(payload, KEY);

function baseConfig(overrides: Partial<CustomConnectorConfig> = {}): CustomConnectorConfig {
  return {
    id: "test-1",
    name: "My Market API",
    baseUrl: "https://api.example.com",
    path: "/quote",
    capabilities: ["PRICE"],
    params: [{ name: "symbol", value: "{{symbol}}", required: true }],
    auth: { scheme: "api_key", header: "X-API-Key" },
    enabled: true,
    ...overrides,
  };
}

function transportReturning(body: string, status = 200): { transport: ConnectorTransport; calls: () => number } {
  let count = 0;
  const transport: ConnectorTransport = async () => {
    count++;
    return {
      status,
      contentType: "application/json",
      text: body,
      bytes: body.length,
      url: "https://api.example.com/quote",
    };
  };
  return { transport, calls: () => count };
}

describe("joinPaths", () => {
  it("preserves a base path prefix", () => {
    expect(joinPaths("/v1", "/quote")).toBe("/v1/quote");
    expect(joinPaths("/v1", "quote")).toBe("/v1/quote");
    expect(joinPaths("/v1/", "/quote")).toBe("/v1/quote");
  });

  it("handles roots and empty paths", () => {
    expect(joinPaths("", "/quote")).toBe("/quote");
    expect(joinPaths("/", "/quote")).toBe("/quote");
    expect(joinPaths("/v1", "")).toBe("/v1");
  });
});

describe("validateHeaders", () => {
  it("accepts ordinary headers", () => {
    expect(() => validateHeaders({ "X-API-Key": "abc", Accept: "application/json" })).not.toThrow();
  });

  it("rejects CRLF injection in names and values", () => {
    expect(() => validateHeaders({ "X-Test": "a\r\nX-Evil: 1" })).toThrow(/line break/);
    expect(() => validateHeaders({ "X-Evil\r\nX-Test": "a" })).toThrow(/line break/);
  });

  it("rejects an empty header name", () => {
    expect(() => validateHeaders({ "  ": "a" })).toThrow(/empty/);
  });
});

describe("buildRequestUrl", () => {
  it("substitutes declared params into the query string", () => {
    expect(buildRequestUrl(baseConfig(), { symbol: "AAPL" })).toBe(
      "https://api.example.com/quote?symbol=AAPL"
    );
  });

  it("preserves a base path prefix such as /v1", () => {
    const url = buildRequestUrl(baseConfig({ baseUrl: "https://api.example.com/v1" }), { symbol: "AAPL" });
    expect(url).toBe("https://api.example.com/v1/quote?symbol=AAPL");
  });

  it("preserves a nested base path", () => {
    const url = buildRequestUrl(
      baseConfig({ baseUrl: "https://api.example.com/api/v1", path: "/quote" }),
      { symbol: "A" }
    );
    expect(url).toBe("https://api.example.com/api/v1/quote?symbol=A");
  });

  it("keeps an existing query string on the base URL", () => {
    const url = buildRequestUrl(baseConfig({ baseUrl: "https://api.example.com?key=abc" }), { symbol: "A" });
    expect(new URL(url).searchParams.get("key")).toBe("abc");
    expect(new URL(url).searchParams.get("symbol")).toBe("A");
  });

  it("percent-encodes values so they cannot inject another parameter", () => {
    const url = buildRequestUrl(baseConfig(), { symbol: "AAPL&admin=1" });
    expect(url).toBe("https://api.example.com/quote?symbol=AAPL%26admin%3D1");
    expect(new URL(url).searchParams.get("admin")).toBeNull();
    expect(new URL(url).searchParams.get("symbol")).toBe("AAPL&admin=1");
  });

  it("encodes placeholders in the path", () => {
    expect(buildRequestUrl(baseConfig({ path: "/quote/{{symbol}}" }), { symbol: "A/B" })).toBe(
      "https://api.example.com/quote/A%2FB?symbol=A%2FB"
    );
  });

  it("encodes path placeholders even with no query params declared", () => {
    expect(buildRequestUrl(baseConfig({ path: "/quote/{{symbol}}", params: [] }), { symbol: "A/B" })).toBe(
      "https://api.example.com/quote/A%2FB"
    );
  });

  it("throws a controlled error for a missing required param", () => {
    expect(() => buildRequestUrl(baseConfig(), {})).toThrow(/Missing required parameter/);
  });

  it("rejects non-https base URLs", () => {
    expect(() => buildRequestUrl(baseConfig({ baseUrl: "http://api.example.com" }), { symbol: "A" })).toThrow(/https/);
  });

  it("keeps literal parameter values literal", () => {
    expect(buildRequestUrl(baseConfig({ params: [{ name: "interval", value: "1d" }] }), {})).toContain("interval=1d");
  });
});

describe("findUndeclaredPlaceholders", () => {
  it("flags placeholders with no declaration", () => {
    const cfg = baseConfig({
      path: "/quote/{{symbol}}/{{date}}",
      params: [{ name: "symbol", value: "{{symbol}}" }],
    });
    expect(findUndeclaredPlaceholders(cfg)).toEqual(["date"]);
  });

  it("returns nothing when all placeholders are declared", () => {
    expect(findUndeclaredPlaceholders(baseConfig())).toEqual([]);
  });
});

describe("custom REST connector fetch", () => {
  it("returns LIVE provenance on success", async () => {
    const { transport } = transportReturning('{"symbol":"AAPL","price":237.42}');
    const connector = buildCustomRestConnector(baseConfig(), { transport });
    const result = await connector.fetch({ capability: "PRICE", params: { symbol: "AAPL" } });
    expect(result.ok).toBe(true);
    expect(result.provenance).toBe("LIVE");
    expect(result.data).toEqual({ symbol: "AAPL", price: 237.42 });
  });

  it("maps 401 to AUTH_FAILED and UNAVAILABLE", async () => {
    const { transport } = transportReturning("unauthorized", 401);
    const connector = buildCustomRestConnector(baseConfig(), { transport });
    const result = await connector.fetch({ capability: "PRICE", params: { symbol: "AAPL" } });
    expect(result.ok).toBe(false);
    expect(result.provenance).toBe("UNAVAILABLE");
    expect(result.error?.code).toBe("auth_failed");
  });

  it("reports unsupported capabilities", async () => {
    const connector = buildCustomRestConnector(baseConfig({ capabilities: ["PRICE"] }));
    const result = await connector.fetch({ capability: "NEWS" });
    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("unsupported_capability");
  });

  it("decrypts the stored credential and sends it as a header", async () => {
    let seen: Record<string, string> | undefined;
    const transport: ConnectorTransport = async (options) => {
      seen = options.headers;
      return { status: 200, contentType: "application/json", text: "{}", bytes: 2, url: options.url };
    };
    const connector = buildCustomRestConnector(
      baseConfig({ authSecretEncrypted: encryptSecret("sk-secret", KEY) }),
      { transport, decrypt }
    );
    await connector.fetch({ capability: "PRICE", params: { symbol: "AAPL" } });
    expect(seen?.["X-API-Key"]).toBe("sk-secret");
  });

  it("never returns the secret in the result", async () => {
    const { transport } = transportReturning('{"ok":true}');
    const connector = buildCustomRestConnector(
      baseConfig({ authSecretEncrypted: encryptSecret("sk-secret", KEY) }),
      { transport, decrypt }
    );
    const result = await connector.fetch({ capability: "PRICE", params: { symbol: "AAPL" } });
    expect(JSON.stringify(result)).not.toContain("sk-secret");
  });

  it("surfaces a parse error for non-JSON bodies", async () => {
    const { transport } = transportReturning("<html></html>");
    const connector = buildCustomRestConnector(baseConfig(), { transport });
    const result = await connector.fetch({ capability: "PRICE", params: { symbol: "A" } });
    expect(result.error?.code).toBe("parse_error");
  });
});

describe("custom REST connector test()", () => {
  it("reports a successful JSON connection without leaking secrets", async () => {
    const body = '{"symbol":"AAPL","price":237.42,"volume":18293421}';
    const { transport } = transportReturning(body);
    const connector = buildCustomRestConnector(
      baseConfig({ authSecretEncrypted: encryptSecret("sk-secret", KEY) }),
      { transport, decrypt }
    );
    const result = await connector.test({ symbol: "AAPL" });
    expect(result.ok).toBe(true);
    expect(result.state).toBe("CONNECTED");
    expect(result.sample).toEqual({ symbol: "AAPL", price: 237.42, volume: 18293421 });
    expect(JSON.stringify(result)).not.toContain("sk-secret");
  });

  it("reports AUTH_FAILED for 403", async () => {
    const { transport } = transportReturning("forbidden", 403);
    const connector = buildCustomRestConnector(baseConfig(), { transport });
    const result = await connector.test({ symbol: "A" });
    expect(result.state).toBe("AUTH_FAILED");
    expect(result.ok).toBe(false);
  });

  it("reports RATE_LIMITED for 429", async () => {
    const { transport } = transportReturning("slow down", 429);
    const connector = buildCustomRestConnector(baseConfig(), { transport });
    expect((await connector.test({ symbol: "A" })).state).toBe("RATE_LIMITED");
  });

  it("reports a timeout as an error", async () => {
    const transport: ConnectorTransport = async () => {
      throw new OutboundError("timeout", "Request timed out after 8000 ms");
    };
    const connector = buildCustomRestConnector(baseConfig(), { transport });
    const result = await connector.test({ symbol: "A" });
    expect(result.ok).toBe(false);
    expect(result.message).toMatch(/timed out/);
  });

  it("reports blocked destinations without network access", async () => {
    const transport: ConnectorTransport = async () => {
      throw new OutboundError("blocked_host", "Host api.internal resolves to blocked address");
    };
    const connector = buildCustomRestConnector(baseConfig(), { transport });
    expect((await connector.test({ symbol: "A" })).message).toMatch(/blocked/);
  });
});

describe("isConfigured", () => {
  it("is false for disabled or misconfigured connectors", () => {
    expect(buildCustomRestConnector(baseConfig({ enabled: false })).isConfigured()).toBe(false);
    expect(buildCustomRestConnector(baseConfig({ baseUrl: "http://x" })).isConfigured()).toBe(false);
    expect(buildCustomRestConnector(baseConfig({ capabilities: [] })).isConfigured()).toBe(false);
    expect(buildCustomRestConnector(baseConfig()).isConfigured()).toBe(true);
  });

  it("namespaces custom connector ids", () => {
    expect(buildCustomRestConnector(baseConfig()).id).toBe("custom:test-1");
  });
});
