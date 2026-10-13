import { describe, expect, it } from "vitest";
import { OutboundError, type SafeGetResult } from "@/lib/connectors/security";
import { webCollectCapability } from "./data-bridge-collect";

const URL_ = "https://example.com/page";

function htmlGet(html: string, overrides: Partial<SafeGetResult> = {}) {
  return async (): Promise<SafeGetResult> => ({
    status: 200,
    contentType: "text/html; charset=utf-8",
    text: html,
    bytes: html.length,
    url: URL_,
    ...overrides,
  });
}

const SELECTOR_HTML = `<!doctype html><html><head><title>Rates</title></head><body>
  <table id="rates"><caption>Swap rates</caption>
    <tr><th>Tenor</th><th>Rate</th></tr>
    <tr><td>5Y</td><td>4.10</td></tr>
    <tr><td>10Y</td><td>4.35</td></tr>
  </table>
  <div class="row"><span class="name">Alpha</span><a class="link" href="/a">Alpha IR</a><span class="px">10.5</span></div>
  <div class="row"><span class="name">Beta</span><a class="link" href="/b">Beta IR</a><span class="px">20.5</span></div>
  <div class="row"><span class="name">Gamma</span><a class="link" href="/c">Gamma IR</a><span class="px">30.5</span></div>
</body></html>`;

describe("web_collect capability", () => {
  it("extracts repeated records with a selector + field map", async () => {
    const result = await webCollectCapability(
      {
        url: URL_,
        selector: ".row",
        fields: { name: ".name", price: ".px" },
      },
      { get: htmlGet(SELECTOR_HTML) },
    );
    expect(result.status).toBe("OK");
    expect(result.extraction).toBe("selector");
    expect(result.matched).toBe(3);
    expect(result.columns).toEqual(["name", "price"]);
    expect(result.rows).toEqual([
      { name: "Alpha", price: "10.5" },
      { name: "Beta", price: "20.5" },
      { name: "Gamma", price: "30.5" },
    ]);
    expect(result.title).toBe("Rates");
  });

  it("reads an attribute instead of text", async () => {
    const result = await webCollectCapability(
      { url: URL_, selector: ".row a", attribute: "href" },
      { get: htmlGet(SELECTOR_HTML) },
    );
    expect(result.rows).toEqual([{ href: "/a" }, { href: "/b" }, { href: "/c" }]);
  });

  it("caps rows and reports the real match count", async () => {
    const result = await webCollectCapability(
      { url: URL_, selector: ".row", maxRows: 2 },
      { get: htmlGet(SELECTOR_HTML) },
    );
    expect(result.rows).toHaveLength(2);
    expect(result.matched).toBe(3);
  });

  it("extracts the page's tables when no selector is given", async () => {
    const result = await webCollectCapability({ url: URL_ }, { get: htmlGet(SELECTOR_HTML) });
    expect(result.status).toBe("OK");
    expect(result.extraction).toBe("tables");
    expect(result.tableCount).toBe(1);
    const tables = result.tables as Array<{ caption: string | null; columns: string[]; rows: string[][] }>;
    expect(tables[0].caption).toBe("Swap rates");
    expect(tables[0].columns).toEqual(["Tenor", "Rate"]);
    expect(tables[0].rows).toEqual([["5Y", "4.10"], ["10Y", "4.35"]]);
  });

  it("a selector with no matches is a confirmed zero, not a failure", async () => {
    const result = await webCollectCapability(
      { url: URL_, selector: ".nope" },
      { get: htmlGet(SELECTOR_HTML) },
    );
    expect(result.status).toBe("OK");
    expect(result.matched).toBe(0);
    expect(result.rows).toEqual([]);
    expect(String(result.note)).toContain("confirmed zero");
  });

  it("refuses a blocked URL before any fetch", async () => {
    let called = false;
    const get = async (): Promise<SafeGetResult> => {
      called = true;
      return { status: 200, contentType: "text/html", text: "", bytes: 0, url: "http://example.com" };
    };
    const result = await webCollectCapability({ url: "http://example.com" }, { get });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("blocked");
    expect(called).toBe(false);
  });

  it("reports a transport failure honestly", async () => {
    const get = async (): Promise<SafeGetResult> => {
      throw new OutboundError("timeout", "timed out");
    };
    const result = await webCollectCapability({ url: URL_ }, { get });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("timeout");
  });

  it("reports a non-2xx response as http_error", async () => {
    const result = await webCollectCapability({ url: URL_ }, { get: htmlGet("nope", { status: 404 }) });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("http_error");
    expect(result.httpStatus).toBe(404);
  });

  it("returns bounded text for a non-HTML document", async () => {
    const result = await webCollectCapability(
      { url: URL_ },
      { get: htmlGet('{"ok":true}', { contentType: "application/json" }) },
    );
    expect(result.status).toBe("OK");
    expect(result.extraction).toBe("text");
    expect(result.text).toBe('{"ok":true}');
  });
});
