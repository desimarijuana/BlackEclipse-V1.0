import { chromium } from 'playwright';

const url = process.argv[2] || 'http://localhost:3999/';
const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message));
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch((e) => console.log('goto:', e.message));
await page.waitForTimeout(6000);

const report = await page.evaluate(() => {
  const cs = (el) => el ? getComputedStyle(el).fontFamily : null;
  const root = document.documentElement;
  const rs = getComputedStyle(root);
  const probe = document.createElement('div');
  probe.className = 'font-sans';
  document.body.appendChild(probe);
  const probeMono = document.createElement('div');
  probeMono.className = 'font-mono';
  document.body.appendChild(probeMono);
  const out = {
    url: location.href,
    htmlClass: root.className,
    varFontSans: rs.getPropertyValue('--font-sans').trim(),
    varFontMono: rs.getPropertyValue('--font-mono').trim(),
    varFontBodoni: rs.getPropertyValue('--font-bodoni').trim(),
    htmlFontFamily: cs(root),
    bodyFontFamily: cs(document.body),
    probeSansFamily: getComputedStyle(probe).fontFamily,
    probeMonoFamily: getComputedStyle(probeMono).fontFamily,
  };
  probe.remove(); probeMono.remove();
  return out;
});
console.log(JSON.stringify(report, null, 2));
console.log('CONSOLE ERRORS:', JSON.stringify(errors.slice(0, 10), null, 2));
await browser.close();
