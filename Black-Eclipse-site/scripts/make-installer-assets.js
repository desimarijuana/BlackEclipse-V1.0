#!/usr/bin/env node
// Generate the bitmap assets the NSIS installer needs.
//
// NSIS only accepts 24-bit BMP, not PNG, and MUI2 wants two fixed sizes:
//   welcome.bmp  164x314  the sidebar shown on Welcome, Finish and Uninstall
//   header.bmp   150x57   the strip drawn on the Install/Uninstall progress page
//
// The artwork is derived from the committed brand SVG, so the installer cannot
// drift from the app icon. The outputs are committed too: a checkout can build
// an installer without running this script or depending on `sharp` (it is only
// a transitive dev dependency).
//
// Usage: node scripts/make-installer-assets.js
//
// Design: dark #08080A panel with the white eclipse mark, the "Black Eclipse"
// wordmark and one lime (#B4FF42) accent — the same language as the boot screen
// (desktop/ui/index.html). The header sits on MUI2's white header band, so it
// uses dark ink on white.

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const SVG = path.join(ROOT, "public", "branding", "LOGO-WORDMARK.svg");
const OUT = path.join(ROOT, "desktop", "installer", "assets");
const ICON = path.join(ROOT, "public", "branding", "black-eclipse.ico");

const BRAND = "#B4FF42";
const INK = "#08080A";

function loadSharp() {
  try {
    return require("sharp");
  } catch {
    throw new Error("sharp is not installed. Run `npm install` before regenerating installer art.");
  }
}

/** Split the brand lockup into its mark (first 4 paths) and wordmark (rest). */
function readLogo() {
  const svg = fs.readFileSync(SVG, "utf8");
  const paths = [...svg.matchAll(/<path\b[^>]*\bd="([^"]+)"/g)].map((m) => m[1]);
  if (paths.length < 5) throw new Error(`Could not parse ${path.relative(ROOT, SVG)}`);
  return { mark: paths.slice(0, 4), wordmark: paths.slice(4) };
}

const pathTags = (ds, fill) =>
  ds.map((d) => `<path d="${d}" fill="${fill}"/>`).join("");

function welcomeSvg(logo) {
  // Mark: the lockup's mark occupies roughly 0..28 x 0..32; render it 86px tall.
  const markScale = 86 / 32;
  const markWidth = 27.6 * markScale;
  const markX = (164 - markWidth) / 2;
  const markY = 58;

  // Wordmark letters start at x≈33.9 in the lockup; strip the mark, keep the
  // type. Scale the 89px-wide wordmark to 120px and centre it.
  const wordScale = 120 / 88.95;
  const wordX = 22 - 33.8973 * wordScale;
  const wordY = 208 - 6.66 * wordScale;

  return `
<svg width="164" height="314" viewBox="0 0 164 314" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="glow" cx="50%" cy="24%" r="62%">
      <stop offset="0%" stop-color="${BRAND}" stop-opacity="0.20"/>
      <stop offset="55%" stop-color="${BRAND}" stop-opacity="0.05"/>
      <stop offset="100%" stop-color="${BRAND}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#141418"/>
      <stop offset="100%" stop-color="${INK}"/>
    </linearGradient>
  </defs>
  <rect width="164" height="314" fill="url(#fade)"/>
  <rect width="164" height="314" fill="url(#glow)"/>
  <circle cx="82" cy="104" r="74" fill="none" stroke="#FFFFFF" stroke-opacity="0.045"/>
  <circle cx="82" cy="104" r="58" fill="none" stroke="#FFFFFF" stroke-opacity="0.06"/>
  <circle cx="140" cy="30" r="3.2" fill="${BRAND}" fill-opacity="0.85"/>
  <g transform="translate(${markX} ${markY}) scale(${markScale})">
    ${pathTags(logo.mark, "#FFFFFF")}
  </g>
  <g transform="translate(${wordX} ${wordY}) scale(${wordScale})">
    ${pathTags(logo.wordmark, "#FFFFFF")}
  </g>
  <rect x="22" y="252" width="120" height="2" rx="1" fill="${BRAND}" fill-opacity="0.9"/>
</svg>`;
}

function headerSvg(logo) {
  const markScale = 26 / 32;
  const markWidth = 27.6 * markScale;
  const markX = 12;
  const markY = (57 - 26) / 2;

  const wordScale = 92 / 88.95;
  const wordX = 46 - 33.8973 * wordScale;
  const wordY = (57 - 18.5 * wordScale) / 2 - 6.66 * wordScale;

  return `
<svg width="150" height="57" viewBox="0 0 150 57" xmlns="http://www.w3.org/2000/svg">
  <rect width="150" height="57" fill="#FFFFFF"/>
  <g transform="translate(${markX} ${markY}) scale(${markScale})">
    ${pathTags(logo.mark, "#0A0A0B")}
  </g>
  <g transform="translate(${wordX} ${wordY}) scale(${wordScale})">
    ${pathTags(logo.wordmark, "#0A0A0B")}
  </g>
  <circle cx="${markX + markWidth + 5}" cy="15" r="2" fill="${BRAND}"/>
</svg>`;
}

/** Write a 24-bit bottom-up BMP (what NSIS and MUI2 accept). */
function writeBmp(file, { data, info }) {
  const { width, height, channels } = info;
  const rowSize = Math.ceil((width * 3) / 4) * 4;
  const pixelBytes = rowSize * height;
  const fileSize = 54 + pixelBytes;
  const buf = Buffer.alloc(fileSize);

  buf.write("BM", 0, "ascii");
  buf.writeUInt32LE(fileSize, 2);
  buf.writeUInt32LE(54, 10);
  buf.writeUInt32LE(40, 14); // BITMAPINFOHEADER
  buf.writeInt32LE(width, 18);
  buf.writeInt32LE(height, 22);
  buf.writeUInt16LE(1, 26);
  buf.writeUInt16LE(24, 28);
  buf.writeUInt32LE(pixelBytes, 34);
  buf.writeInt32LE(2835, 38);
  buf.writeInt32LE(2835, 42);

  for (let y = 0; y < height; y += 1) {
    const srcRow = (height - 1 - y) * width * channels;
    const dstRow = 54 + y * rowSize;
    for (let x = 0; x < width; x += 1) {
      const s = srcRow + x * channels;
      const d = dstRow + x * 3;
      // sharp returns RGBA; BMP stores BGR.
      buf[d] = data[s + 2];
      buf[d + 1] = data[s + 1];
      buf[d + 2] = data[s];
    }
  }

  fs.writeFileSync(file, buf);
  return { width, height, bytes: fileSize };
}

async function main() {
  const sharp = loadSharp();
  if (!fs.existsSync(ICON)) throw new Error(`Brand icon missing: ${ICON}`);
  fs.mkdirSync(OUT, { recursive: true });

  const logo = readLogo();
  const jobs = [
    { name: "welcome.bmp", svg: welcomeSvg(logo), width: 164, height: 314 },
    { name: "header.bmp", svg: headerSvg(logo), width: 150, height: 57 },
  ];

  for (const job of jobs) {
    const { data, info } = await sharp(Buffer.from(job.svg))
      .resize(job.width, job.height)
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const written = writeBmp(path.join(OUT, job.name), { data, info });
    console.log(`  ${job.name}  ${written.width}x${written.height}  ${written.bytes} bytes`);
  }

  // One icon for both the installer and the uninstaller: the same multi-size
  // .ico the app already ships, so Explorer draws the eclipse mark, not the
  // stock NSIS globe.
  fs.copyFileSync(ICON, path.join(OUT, "icon.ico"));
  console.log(`  icon.ico  (copy of ${path.relative(ROOT, ICON)})`);
  console.log(`\nWrote ${path.relative(ROOT, OUT)}`);
}

main().catch((err) => {
  console.error(`make-installer-assets: ${err.message}`);
  process.exit(1);
});
