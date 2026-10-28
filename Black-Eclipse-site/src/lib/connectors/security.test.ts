import { describe, it, expect } from "vitest";
import {
  validateOutboundUrl,
  isBlockedAddress,
  parseIpv6,
  normalizeHostname,
  redactUrl,
  readCappedBody,
  createPinnedLookup,
  safeGet,
  safePost,
  MAX_REQUEST_BYTES,
  OutboundError,
  DEFAULT_MAX_BYTES,
  type LookupAllFn,
} from "./security";
import { EventEmitter } from "node:events";

describe("validateOutboundUrl", () => {
  it("accepts public https URLs", () => {
    expect(validateOutboundUrl("https://api.binance.com/api/v3/ticker").safe).toBe(true);
    expect(validateOutboundUrl("https://example.com/x?symbol=AAPL").safe).toBe(true);
  });

  it("rejects non-https protocols", () => {
    expect(validateOutboundUrl("http://example.com/").safe).toBe(false);
    expect(validateOutboundUrl("file:///etc/passwd").safe).toBe(false);
    expect(validateOutboundUrl("ftp://example.com/x").safe).toBe(false);
  });

  it("rejects embedded credentials", () => {
    expect(validateOutboundUrl("https://user:pass@example.com/").safe).toBe(false);
  });

  it("rejects localhost and private hosts", () => {
    expect(validateOutboundUrl("https://localhost/x").safe).toBe(true); // hostname, resolved later
    expect(validateOutboundUrl("https://127.0.0.1/x").safe).toBe(false);
    expect(validateOutboundUrl("https://10.0.0.5/x").safe).toBe(false);
    expect(validateOutboundUrl("https://192.168.1.1/x").safe).toBe(false);
    expect(validateOutboundUrl("https://169.254.169.254/latest/meta-data").safe).toBe(false);
  });

  it("blocks alternate IPv4 encodings via WHATWG normalization", () => {
    expect(validateOutboundUrl("https://2130706433/").safe).toBe(false); // 127.0.0.1
    expect(validateOutboundUrl("https://0x7f000001/").safe).toBe(false);
    expect(validateOutboundUrl("https://0177.0.0.1/").safe).toBe(false);
    expect(validateOutboundUrl("https://127.1/").safe).toBe(false);
    expect(validateOutboundUrl("https://0/").safe).toBe(false);
  });

  it("blocks IPv6 loopback and mapped forms", () => {
    expect(validateOutboundUrl("https://[::1]/").safe).toBe(false);
    expect(validateOutboundUrl("https://[::ffff:127.0.0.1]/").safe).toBe(false);
    expect(validateOutboundUrl("https://[fe80::1]/").safe).toBe(false);
    expect(validateOutboundUrl("https://[fc00::1]/").safe).toBe(false);
  });

  it("rejects malformed URLs", () => {
    expect(validateOutboundUrl("not a url").safe).toBe(false);
  });
});

describe("isBlockedAddress", () => {
  it("classifies IPv4 ranges", () => {
    expect(isBlockedAddress("127.0.0.1")).toBe(true);
    expect(isBlockedAddress("0.0.0.0")).toBe(true);
    expect(isBlockedAddress("10.1.2.3")).toBe(true);
    expect(isBlockedAddress("172.16.0.1")).toBe(true);
    expect(isBlockedAddress("172.32.0.1")).toBe(false);
    expect(isBlockedAddress("192.168.0.1")).toBe(true);
    expect(isBlockedAddress("169.254.169.254")).toBe(true);
    expect(isBlockedAddress("100.100.100.200")).toBe(true);
    expect(isBlockedAddress("8.8.8.8")).toBe(false);
    expect(isBlockedAddress("93.184.216.34")).toBe(false);
  });

  it("classifies IPv6 ranges", () => {
    expect(isBlockedAddress("::1")).toBe(true);
    expect(isBlockedAddress("::")).toBe(true);
    expect(isBlockedAddress("fe80::1")).toBe(true);
    expect(isBlockedAddress("fc00::1")).toBe(true);
    expect(isBlockedAddress("fd12::1")).toBe(true);
    expect(isBlockedAddress("2606:4700:4700::1111")).toBe(false);
  });

  it("classifies IPv4-mapped IPv6 by the embedded address", () => {
    expect(isBlockedAddress("::ffff:127.0.0.1")).toBe(true);
    expect(isBlockedAddress("::ffff:10.0.0.1")).toBe(true);
    expect(isBlockedAddress("::ffff:8.8.8.8")).toBe(false);
  });
});

describe("parseIpv6", () => {
  it("expands compressed and full forms", () => {
    expect(parseIpv6("::1")).toEqual([0, 0, 0, 0, 0, 0, 0, 1]);
    expect(parseIpv6("::ffff:7f00:1")).toEqual([0, 0, 0, 0, 0, 0xffff, 0x7f00, 1]);
    expect(parseIpv6("2606:4700:4700::1111")?.length).toBe(8);
  });

  it("returns null for malformed input", () => {
    expect(parseIpv6("not-an-ip")).toBeNull();
    expect(parseIpv6("1:2:3")).toBeNull();
  });
});

describe("normalizeHostname", () => {
  it("strips IPv6 brackets", () => {
    expect(normalizeHostname("[::1]")).toBe("::1");
    expect(normalizeHostname("example.com")).toBe("example.com");
  });
});

describe("redactUrl", () => {
  it("drops query strings and credentials", () => {
    expect(redactUrl("https://api.example.com/quote?apikey=secret&symbol=AAPL")).toBe(
      "https://api.example.com/quote"
    );
    expect(redactUrl("nonsense")).toBe("<invalid-url>");
  });
});

describe("createPinnedLookup", () => {
  const resolver = (addresses: Array<{ address: string; family: number }>): LookupAllFn => (_h, _o, cb) =>
    cb(null, addresses);

  it("returns a single address when the caller asks for one", () => {
    const lookup = createPinnedLookup(resolver([{ address: "8.8.8.8", family: 4 }]));
    lookup("example.com", {}, (err, address, family) => {
      expect(err).toBeNull();
      expect(address).toBe("8.8.8.8");
      expect(family).toBe(4);
    });
  });

  it("returns an array when happy-eyeballs asks for all (Node 20 autoSelectFamily)", () => {
    const lookup = createPinnedLookup(
      resolver([
        { address: "8.8.8.8", family: 4 },
        { address: "2606:4700:4700::1111", family: 6 },
      ])
    );
    lookup("example.com", { all: true }, (err, address) => {
      expect(err).toBeNull();
      expect(Array.isArray(address)).toBe(true);
      expect(address).toHaveLength(2);
    });
  });

  it("rejects at connect time when DNS resolves to a private address (rebinding)", () => {
    const lookup = createPinnedLookup(resolver([{ address: "127.0.0.1", family: 4 }]));
    lookup("evil.example.com", {}, (err, address) => {
      expect(err?.code).toBe("EBLOCKEDHOST");
      expect(address).toBe("");
    });
  });

  it("rejects when ANY resolved address is private", () => {
    const lookup = createPinnedLookup(
      resolver([
        { address: "8.8.8.8", family: 4 },
        { address: "10.0.0.1", family: 4 },
      ])
    );
    lookup("mixed.example.com", {}, (err) => expect(err?.code).toBe("EBLOCKEDHOST"));
  });
});

// ── Bounded redirect following (Phase 7) ────────────────────────────────────
// Official regulator/exchange hosts commonly 301/302. Following is bounded and
// re-validates every hop; a non-https or blocked target is refused.

function fakeResponse(status: number, headers: Record<string, string>, body: string) {
  const res = new EventEmitter() as unknown as {
    statusCode: number;
    headers: Record<string, string>;
    destroy: () => void;
    [Symbol.asyncIterator]: () => AsyncIterableIterator<Uint8Array>;
  };
  (res as { statusCode: number }).statusCode = status;
  (res as { headers: Record<string, string> }).headers = headers;
  (res as { destroy: () => void }).destroy = () => undefined;
  (res as unknown as { [Symbol.asyncIterator]: () => AsyncIterableIterator<Uint8Array> })[
    Symbol.asyncIterator
  ] = async function* () {
    yield Buffer.from(body);
  };
  return res;
}

describe("safeGet redirect handling", () => {
  const lookupAll: LookupAllFn = (_h, _o, cb) => cb(null, [{ address: "93.184.216.34", family: 4 }]);

  it("does not follow a redirect by default", async () => {
    const request = ((_u: unknown, _o: unknown, cb: (r: unknown) => void) => {
      const req = new EventEmitter() as unknown as { end: () => void };
      req.end = () => cb(fakeResponse(302, { location: "https://example.com/next" }, ""));
      return req;
    }) as never;
    await expect(
      safeGet({ url: "https://example.com/a" }, { lookupAll, request })
    ).rejects.toMatchObject({ code: "redirect" });
  });

  it("follows a bounded https redirect when maxRedirects is set", async () => {
    let call = 0;
    const request = ((_u: unknown, _o: unknown, cb: (r: unknown) => void) => {
      const req = new EventEmitter() as unknown as { end: () => void };
      req.end = () => {
        call += 1;
        cb(
          call === 1
            ? fakeResponse(301, { location: "https://example.com/final" }, "")
            : fakeResponse(200, { "content-type": "text/html" }, "done")
        );
      };
      return req;
    }) as never;
    const result = await safeGet(
      { url: "https://example.com/a", maxRedirects: 3 },
      { lookupAll, request }
    );
    expect(result.status).toBe(200);
    expect(result.text).toBe("done");
    expect(call).toBe(2);
  });

  it("refuses a redirect to a non-https target", async () => {
    const request = ((_u: unknown, _o: unknown, cb: (r: unknown) => void) => {
      const req = new EventEmitter() as unknown as { end: () => void };
      // A real bot-wall (perfdrive) redirects to http://; refuse it.
      req.end = () => cb(fakeResponse(302, { location: "http://validate.perfdrive.com/x" }, ""));
      return req;
    }) as never;
    await expect(
      safeGet({ url: "https://www.sedarplus.ca/", maxRedirects: 3 }, { lookupAll, request })
    ).rejects.toMatchObject({ code: "redirect" });
  });

  it("re-validates each hop (a redirect to a private address is blocked)", async () => {
    const request = ((_u: unknown, _o: unknown, cb: (r: unknown) => void) => {
      const req = new EventEmitter() as unknown as { end: () => void };
      req.end = () => cb(fakeResponse(302, { location: "https://127.0.0.1/secret" }, ""));
      return req;
    }) as never;
    await expect(
      safeGet({ url: "https://example.com/a", maxRedirects: 3 }, { lookupAll, request })
    ).rejects.toBeInstanceOf(OutboundError);
  });
});

describe("safePost", () => {
  const lookupAll: LookupAllFn = (_h, _o, cb) => cb(null, [{ address: "93.184.216.34", family: 4 }]);

  it("sends a POST with the caller body and a content-length", async () => {
    let seenMethod = "";
    let written = "";
    const request = ((_u: unknown, opts: { method?: string }, cb: (r: unknown) => void) => {
      seenMethod = String(opts.method);
      const req = new EventEmitter() as unknown as { write: (b: unknown) => void; end: () => void };
      req.write = (b: unknown) => { written = String(b); };
      req.end = () => cb(fakeResponse(200, { "content-type": "application/json" }, '{"ok":true}'));
      return req;
    }) as never;
    const result = await safePost(
      { url: "https://api.hyperliquid.xyz/info", body: '{"type":"l2Book","coin":"BTC"}' },
      { lookupAll, request }
    );
    expect(seenMethod).toBe("POST");
    expect(written).toContain("l2Book");
    expect(result.status).toBe(200);
    expect(result.text).toBe('{"ok":true}');
  });

  it("does not follow a redirect", async () => {
    const request = ((_u: unknown, _o: unknown, cb: (r: unknown) => void) => {
      const req = new EventEmitter() as unknown as { write: () => void; end: () => void };
      req.write = () => undefined;
      req.end = () => cb(fakeResponse(307, { location: "https://example.com/next" }, ""));
      return req;
    }) as never;
    await expect(
      safePost({ url: "https://example.com/a", body: "{}" }, { lookupAll, request })
    ).rejects.toMatchObject({ code: "redirect" });
  });

  it("refuses an oversized request body before any connection", async () => {
    let called = false;
    const request = (() => { called = true; throw new Error("should not connect"); }) as never;
    await expect(
      safePost(
        { url: "https://example.com/a", body: Buffer.alloc(MAX_REQUEST_BYTES + 1) },
        { lookupAll, request }
      )
    ).rejects.toMatchObject({ code: "too_large" });
    expect(called).toBe(false);
  });
});

describe("readCappedBody", () => {
  async function* stream(chunks: Uint8Array[]): AsyncIterable<Uint8Array> {
    for (const c of chunks) yield c;
  }

  it("accumulates under the cap", async () => {
    const body = await readCappedBody(stream([Buffer.from("hello "), Buffer.from("world")]), 100);
    expect(body.text).toBe("hello world");
    expect(body.bytes).toBe(11);
  });

  it("throws OutboundError once the cap is exceeded", async () => {
    const big = Buffer.alloc(64);
    await expect(readCappedBody(stream([big, big]), 100)).rejects.toBeInstanceOf(OutboundError);
  });

  it("default cap is a positive, bounded value", () => {
    expect(DEFAULT_MAX_BYTES).toBeGreaterThan(0);
    expect(DEFAULT_MAX_BYTES).toBeLessThanOrEqual(10 * 1024 * 1024);
  });
});
