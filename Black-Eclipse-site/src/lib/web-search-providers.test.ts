import { describe, expect, it, vi, afterEach } from "vitest";
import {
  BingHtmlProvider,
  DuckDuckGoHtmlProvider,
  DuckDuckGoLiteProvider,
  MojeekProvider,
  keylessSearchProviders,
  unwrapBing,
} from "@/lib/web-search";

// The keyless default is a CHAIN of independent HTML endpoints, so one engine
// being bot-blocked no longer blanks a search. These tests pin the chain, the
// block/zero-result distinction, and the link-unwrapping helpers.

afterEach(() => {
  vi.restoreAllMocks();
});

describe("keyless search provider chain", () => {
  it("lists independent providers in preference order", () => {
    const ids = keylessSearchProviders().map((p) => p.id);
    expect(ids).toEqual(["duckduckgo-html", "duckduckgo-lite", "mojeek", "bing-html"]);
    // Distinct transport surfaces, not the same endpoint four times.
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("every keyless provider is always configured", async () => {
    for (const p of keylessSearchProviders()) {
      expect(await Promise.resolve(p.configured())).toBe(true);
    }
  });
});

describe("block vs zero-result diagnosis", () => {
  it("classifies an HTTP 202 challenge page as blocked", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html>please verify you are human</html>", { status: 202 })
    );
    const attempt = await new DuckDuckGoHtmlProvider().search("nvda", 5);
    expect(attempt.results).toEqual([]);
    expect(attempt.diagnostic.category).toBe("blocked");
    expect(attempt.diagnostic.retryable).toBe(false);
  });

  it("classifies a 200 page with no results as zero_results, not blocked", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html><body>no results here</body></html>", { status: 200 })
    );
    const attempt = await new MojeekProvider().search("nvda", 5);
    expect(attempt.results).toEqual([]);
    expect(attempt.diagnostic.category).toBe("zero_results");
    expect(attempt.diagnostic.normalizedStatus).toBe("ok");
  });
});

describe("unwrapBing", () => {
  it("recovers the real URL from a bing.com/ck/a click tracker", () => {
    // base64url("https://example.com/page") with Bing's "a1" prefix and padding.
    const target = "https://example.com/page";
    const b64 = Buffer.from(target, "utf8").toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const wrapped = `https://www.bing.com/ck/a?u=a1${b64}&ntb=1`;
    expect(unwrapBing(wrapped)).toBe(target);
  });

  it("leaves a non-Bing URL unchanged", () => {
    expect(unwrapBing("https://example.com/x")).toBe("https://example.com/x");
  });
});

describe("Bing parse", () => {
  it("extracts title/url/snippet from b_algo blocks", async () => {
    const target = "https://example.com/page";
    const b64 = Buffer.from(target, "utf8").toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const html = `<html><body><ol id="b_results"><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1${b64}">Example Title</a></h2><div class="b_caption"><p>Example snippet text.</p></div></li></ol></body></html>`;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(html, { status: 200 }));
    const attempt = await new BingHtmlProvider().search("example", 5);
    expect(attempt.results).toHaveLength(1);
    expect(attempt.results[0].url).toBe(target);
    expect(attempt.results[0].title).toBe("Example Title");
  });
});

describe("DuckDuckGo Lite parse", () => {
  it("recovers the uddg redirect URL and snippet", async () => {
    const real = "https://example.org/story";
    const html = `<html><body><table><tr><td><a class="result-link" href="//duckduckgo.com/l/?uddg=${encodeURIComponent(real)}">Story Title</a></td></tr><tr><td class="result-snippet">A short snippet.</td></tr></table></body></html>`;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(html, { status: 200 }));
    const attempt = await new DuckDuckGoLiteProvider().search("story", 5);
    expect(attempt.results).toHaveLength(1);
    expect(attempt.results[0].url).toBe(real);
  });
});
