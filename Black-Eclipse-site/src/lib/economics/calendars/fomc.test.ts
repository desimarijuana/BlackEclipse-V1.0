import { describe, expect, it } from "vitest";
import { parseFomcCalendar } from "./fomc";

const HTML = `
<div class="panel panel-default">
  <div class="panel-heading"><h4><a id="42828">2026 FOMC Meetings</a></h4></div>
  <div class="row fomc-meeting">
    <div class="fomc-meeting__month"><strong>January</strong></div>
    <div class="fomc-meeting__date">27-28</div>
  </div>
  <div class="fomc-meeting--shaded row fomc-meeting">
    <div class="fomc-meeting__month"><strong>March</strong></div>
    <div class="fomc-meeting__date">17-18*</div>
  </div>
  <div class="row fomc-meeting">
    <div class="fomc-meeting__month"><strong>April</strong></div>
    <div class="fomc-meeting__date">28-29</div>
  </div>
  <div class="row fomc-meeting">
    <div class="fomc-meeting__month"><strong>August</strong></div>
    <div class="fomc-meeting__date">22 (notation vote)</div>
  </div>
</div>
<div class="panel panel-default">
  <div class="panel-heading"><h4><a id="45694">2027 FOMC Meetings</a></h4></div>
  <div class="row fomc-meeting">
    <div class="fomc-meeting__month"><strong>January</strong></div>
    <div class="fomc-meeting__date">26-27</div>
  </div>
</div>
<div class="panel panel-default">
  <div class="panel-heading"><h4><a>Other panel</a></h4></div>
  <div class="row fomc-meeting">
    <div class="fomc-meeting__month"><strong>January</strong></div>
    <div class="fomc-meeting__date">1-2</div>
  </div>
</div>
`;

describe("parseFomcCalendar", () => {
  it("reads the decision day from each year panel and skips non-FOMC panels", () => {
    const meetings = parseFomcCalendar(HTML, "https://example.test/fomc");
    expect(meetings.map((m) => m.date)).toEqual([
      "2026-01-28",
      "2026-03-18",
      "2026-04-29",
      "2027-01-27",
    ]);
    expect(meetings[0]).toMatchObject({
      title: "FOMC Interest Rate Decision",
      country: "US",
      confirmed: true,
      source: "official",
      url: "https://example.test/fomc",
    });
  });

  it("preserves the Fed's tentative marker instead of guessing", () => {
    const meetings = parseFomcCalendar(HTML);
    expect(meetings.find((m) => m.date === "2026-03-18")?.confirmed).toBe(false);
  });

  it("returns an empty list when nothing is parseable — never a synthetic date", () => {
    expect(parseFomcCalendar("<html><body>maintenance</body></html>")).toEqual([]);
  });
});
