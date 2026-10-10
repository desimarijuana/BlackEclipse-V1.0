import { describe, it, expect } from 'vitest';
import { parsePsxFinancials, psxYearsToPeriods } from './psx';

// Real shape from https://dps.psx.com.pk/company/OGDC (Annual tab). Note the
// exchange's page nests <tbody> inside <thead> — the parser must tolerate it.
const FIXTURE = `
<div class="section section--padded company" id="financials"><div class="company__financials">
<h1 class="section__title">Financials</h1>
<p style="color:#666; float:left;">All numbers in thousands (000's) except EPS</p>
<div class="tabs__panels">
<div class="tabs__panel" data-name="Annual"><div class="tbl__wrapper">
<table class="tbl tbl--col-striped">
  <thead class="tbl__head"><tr><th></th><th class="right">2026</th><th class="right">2025</th><th class="right">2024</th><th class="right">2023</th>
  <tbody class="tbl__body">
    <tr><td>Sales</td><td class="right"><span>449,190,752</span></td><td class="right"><span>401,177,969</span></td><td class="right"><span>463,697,861</span></td><td class="right"><span>413,594,009</span></td></tr>
    <tr><td>Profit after Taxation</td><td class="right"><span>242,373,646</span></td><td class="right"><span>169,903,614</span></td><td class="right"><span>208,975,771</span></td><td class="right"><span>224,617,797</span></td></tr>
    <tr><td>EPS</td><td class="right"><span>56.35</span></td><td class="right"><span>39.50</span></td><td class="right"><span>48.59</span></td><td class="right"><span>52.23</span></td></tr>
  </tbody></thead>
</table>
</div></div>
<div class="tabs__panel" data-name="Quarterly"><div class="tbl__wrapper">
  <table><thead><tr><th></th><th>Q3 2026</th></tr></thead><tbody><tr><td>Sales</td><td>107,297,009</td></tr></tbody></table>
</div></div>
</div></div></div>
`;

describe('parsePsxFinancials', () => {
  it('extracts the annual table, scales thousands, sorts oldest→newest', () => {
    const years = parsePsxFinancials(FIXTURE);
    expect(years.map((y) => y.fiscalYear)).toEqual([2023, 2024, 2025, 2026]);
    const y2026 = years.find((y) => y.fiscalYear === 2026)!;
    expect(y2026.revenue).toBe(449_190_752_000); // thousands → base
    expect(y2026.netIncome).toBe(242_373_646_000);
    expect(y2026.eps).toBe(56.35); // EPS is not scaled
    const y2024 = years.find((y) => y.fiscalYear === 2024)!;
    expect(y2024.revenue).toBe(463_697_861_000);
  });

  it('returns [] when the financials section is absent', () => {
    expect(parsePsxFinancials('<html><body>No table</body></html>')).toEqual([]);
    expect(parsePsxFinancials('')).toEqual([]);
  });

  it('maps to provider periods with the PK fiscal-year-end date', () => {
    const periods = psxYearsToPeriods(parsePsxFinancials(FIXTURE));
    expect(periods).toHaveLength(4);
    expect(periods[3].endDate).toBe('2026-06-30');
    expect(periods[3].revenue).toBe(449_190_752_000);
    expect(periods[3].fiscalYear).toBe(2026);
  });
});
