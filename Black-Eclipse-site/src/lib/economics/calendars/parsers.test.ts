import { describe, expect, it } from "vitest";
import { parseBlsSchedule } from "./bls";
import { parseBeaSchedule } from "./bea";
import { parseEcbSchedule } from "./ecb";
import { parseBoeSchedule } from "./boe";
import { parseBojSchedule } from "./boj";

describe("official schedule parsers", () => {
  it("BLS: reads the explicit release date and time", () => {
    const html = `
      <table class="release-list"><thead><tr><th>Reference Month</th><th>Release Date</th><th>Release Time</th></tr></thead>
      <tbody>
        <tr class="release-list-even-row"><td>October 2026</td><td>Nov. 10, 2026</td><td>08:30 AM</td></tr>
        <tr class="release-list-odd-row"><td>November 2026</td><td>Dec. 10, 2026</td><td>08:30 AM</td></tr>
      </tbody></table>`;
    const events = parseBlsSchedule(html, { title: "US Consumer Price Index (CPI)", url: "https://www.bls.gov/x" });
    expect(events.map((e) => e.date)).toEqual(["2026-11-10", "2026-12-10"]);
    expect(events[0]).toMatchObject({ time: "08:30 AM ET", country: "US", importance: "high" });
  });

  it("BEA: keeps GDP/PCE rows and ignores unrelated releases", () => {
    const html = `
      <table id="release-schedule-table"><thead><tr><th>Year 2026</th><th></th><th>Release</th></tr></thead>
      <tbody>
        <tr><td class="scheduled-date"><div class="release-date">November 17</div><small class="text-muted">10:00 AM</small></td><td></td><td class="release-title">Experimental Statistics, 2024</td></tr>
        <tr><td class="scheduled-date"><div class="release-date">November 25</div><small class="text-muted">8:30 AM</small></td><td></td><td class="release-title">Gross Domestic Product, 3rd Quarter 2026 (Second Estimate)</td></tr>
        <tr><td class="scheduled-date"><div class="release-date">December 23</div><small class="text-muted">8:30 AM</small></td><td></td><td class="release-title">Personal Income and Outlays, November 2026</td></tr>
      </tbody></table>`;
    const events = parseBeaSchedule(html);
    expect(events.map((e) => e.title)).toEqual(["US GDP Release", "US PCE Inflation"]);
    expect(events.map((e) => e.date)).toEqual(["2026-11-25", "2026-12-23"]);
  });

  it("ECB: keeps the decision day (Day 2) and drops non-monetary meetings", () => {
    const html = `
      <dl>
        <dt>25/11/2026</dt><dd>Governing Council of the ECB: non-monetary policy meeting (in Frankfurt)<br></dd>
        <dt>16/12/2026</dt><dd>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 1)<br></dd>
        <dt>17/12/2026</dt><dd>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 2), followed by press conference<br></dd>
      </dl>`;
    const events = parseEcbSchedule(html);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ date: "2026-12-17", country: "EU", title: "ECB Interest Rate Decision" });
  });

  it("BoE: derives the year from the section heading", () => {
    const html = `
      <h2>2026 confirmed dates</h2>
      <table><tbody>
        <tr><td>Thursday 5 February</td><td>February MPC Summary and minutes</td></tr>
        <tr><td>Thursday&nbsp;17 December</td><td>December MPC Summary and minutes</td></tr>
      </tbody></table>
      <h2>2027 confirmed dates</h2>
      <table><tbody>
        <tr><td>Thursday 4 February</td><td>February MPC Summary and minutes</td></tr>
      </tbody></table>`;
    const events = parseBoeSchedule(html);
    expect(events.map((e) => e.date)).toEqual(["2026-02-05", "2026-12-17", "2027-02-04"]);
    expect(events.every((e) => e.confirmed)).toBe(true);
  });

  it("BoJ: takes the final day of a two-day meeting", () => {
    const html = `
      <h2 id="p2026">2026</h2>
      <table><tbody>
        <tr><td><a href="/k260123a.pdf">Jan. 22 (Thurs.), 23 (Fri.) [PDF]</a></td><td></td></tr>
        <tr><td><a href="/k260319a.pdf">Mar. 18 (Wed.), 19 (Thurs.) [PDF]</a></td><td></td></tr>
      </tbody></table>
      <h2 id="p2027">2027</h2>
      <table><tbody>
        <tr><td><a href="/k270122a.pdf">Jan. 21 (Thurs.), 22 (Fri.) [PDF]</a></td><td></td></tr>
      </tbody></table>`;
    const events = parseBojSchedule(html);
    expect(events.map((e) => e.date)).toEqual(["2026-01-23", "2026-03-19", "2027-01-22"]);
    expect(events[0].time).toBeNull();
  });
});
