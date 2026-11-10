import { describe, expect, it, vi, beforeEach } from "vitest";

const safeGet = vi.fn();
vi.mock("@/lib/connectors/security", () => ({
  safeGet: (...args: unknown[]) => safeGet(...args),
}));

import {
  parsePsxAnnouncements,
  fetchPsxAnnouncements,
  toPsxFilingRows,
  __resetPsxAnnouncementsCache,
} from "./psx-announcements";

const HTML = `
<div id="announcements">
  <table><thead><tr><th>Date</th><th>Title</th><th>Document</th></tr></thead><tbody>
    <tr><td>Oct 29, 2024</td><td>FINANCIAL RESULTS FOR THE NINE MONTHS ENDED SEPTEMBER 30, 2024 </td>
        <td><a href="/download/document/241100.pdf" target="_blank">PDF</a></td></tr>
    <tr><td>Aug 22, 2024</td><td>SIX MONTHS RESULTS</td>
        <td><a href="javascript:" data-images="235567-1.gif">View</a></td></tr>
  </tbody></table>
  <table><tbody>
    <tr><td>Dec 2, 2024</td><td>EMERGENT BOARD MEETING</td>
        <td><a href="/download/document/243720.pdf">PDF</a></td></tr>
  </tbody></table>
  <table><tbody>
    <tr><td>Dec 27, 2024</td><td>BOOK CLOSURE NOTICE</td>
        <td><a href="/download/document/245099.pdf">PDF</a></td></tr>
  </tbody></table>
</div>`;

describe("parsePsxAnnouncements", () => {
  it("reads all three announcement tables, newest first", () => {
    const items = parsePsxAnnouncements(HTML);
    expect(items.map((i) => i.date)).toEqual([
      "2024-12-27",
      "2024-12-02",
      "2024-10-29",
      "2024-08-22",
    ]);
    expect(items.map((i) => i.category)).toEqual([
      "Others",
      "Board Meetings",
      "Financial Results",
      "Financial Results",
    ]);
  });

  it("builds the official PDF URL and keeps the document id", () => {
    const items = parsePsxAnnouncements(HTML);
    const pdf = items.find((i) => i.date === "2024-10-29");
    expect(pdf).toMatchObject({
      documentId: "241100",
      url: "https://dps.psx.com.pk/download/document/241100.pdf",
    });
  });

  it("keeps an image-only announcement without inventing a URL", () => {
    const image = parsePsxAnnouncements(HTML).find((i) => i.date === "2024-08-22");
    expect(image).toMatchObject({ url: null, documentId: "235567" });
  });

  it("returns [] for a page without announcements", () => {
    expect(parsePsxAnnouncements("<html></html>")).toEqual([]);
  });

  it("normalizes to the shared filing-list row shape", () => {
    const [row] = toPsxFilingRows(parsePsxAnnouncements(HTML));
    expect(row).toMatchObject({
      form: "Others",
      filed: "2024-12-27",
      description: "BOOK CLOSURE NOTICE",
    });
  });
});

describe("fetchPsxAnnouncements", () => {
  beforeEach(() => {
    safeGet.mockReset();
    __resetPsxAnnouncementsCache();
  });

  it("fetches the company page and caches per symbol", async () => {
    safeGet.mockResolvedValue({ status: 200, text: HTML, headers: {}, url: "x", contentType: "text/html", bytes: HTML.length });
    const first = await fetchPsxAnnouncements("engro", { now: () => 1000 });
    expect(first).toHaveLength(4);
    expect(safeGet.mock.calls[0][0].url).toBe("https://dps.psx.com.pk/company/ENGRO");

    await fetchPsxAnnouncements("ENGRO", { now: () => 2000 });
    expect(safeGet).toHaveBeenCalledTimes(1);
  });

  it("throws when the exchange returns nothing parseable", async () => {
    safeGet.mockResolvedValue({ status: 200, text: "<html></html>", headers: {}, url: "x", contentType: "text/html", bytes: 13 });
    await expect(fetchPsxAnnouncements("ENGRO")).rejects.toThrow(/no announcements/);
  });

  it("surfaces an HTTP failure", async () => {
    safeGet.mockResolvedValue({ status: 503, text: "", headers: {}, url: "x", contentType: null, bytes: 0 });
    await expect(fetchPsxAnnouncements("ENGRO")).rejects.toThrow(/HTTP 503/);
  });
});
