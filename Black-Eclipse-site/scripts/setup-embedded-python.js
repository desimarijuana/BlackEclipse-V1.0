#!/usr/bin/env node
// Downloads and installs an embedded (portable) Python into the repo so the
// yfinance/scrapling bridges work for new users WITHOUT requiring a system
// Python install. Uses the official Windows "embeddable" zip + get-pip.
//
//   node scripts/setup-embedded-python.js   → install into scripts/vendor/python
//   node scripts/setup-embedded-python.js --check → exit 0 if usable, 1 if not
//
// Only runs on Windows (the embed zip is Windows-specific). On macOS/Linux it
// falls back to the system python3 (no vendoring needed).

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const https = require("https");

const VERSION = "3.12.8";
const EMBED_URL = `https://www.python.org/ftp/python/${VERSION}/python-${VERSION}-embed-amd64.zip`;
const GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py";
const VENDOR_DIR = path.join(__dirname, "vendor", "python");
const PYTHON_EXE = path.join(VENDOR_DIR, "python.exe");
const MARKER = path.join(VENDOR_DIR, ".ready");

const log = (m) => console.log(`[py] ${m}`);

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https
      .get(url, (res) => {
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode} for ${url}`));
          res.resume();
          return;
        }
        res.pipe(file);
        file.on("finish", () => file.close(() => resolve(dest)));
      })
      .on("error", (err) => {
        fs.unlinkSync(dest);
        reject(err);
      });
  });
}

function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: opts.stdio ?? "pipe", timeout: opts.timeout ?? 300000, ...opts });
}

function ready() {
  return fs.existsSync(PYTHON_EXE) && fs.existsSync(MARKER);
}

async function install() {
  if (process.platform !== "win32") {
    log("non-Windows — rely on system python3, nothing to vendor");
    return;
  }
  if (ready()) {
    log(`embedded Python already installed at ${VENDOR_DIR}`);
    return;
  }
  log(`downloading embedded Python ${VERSION}...`);
  fs.mkdirSync(VENDOR_DIR, { recursive: true });
  const zip = path.join(VENDOR_DIR, "embed.zip");
  await download(EMBED_URL, zip);

  log("extracting...");
  // tar (libarchive, ships with Windows 10+ / macOS / Linux) extracts the zip.
  try {
    run(`tar -xf "${zip}" -C "${VENDOR_DIR}"`);
  } catch {
    // Fallback: PowerShell Expand-Archive.
    run(`powershell -NoProfile -Command "Expand-Archive -Force -Path '${zip}' -DestinationPath '${VENDOR_DIR}'"`);
  }
  fs.unlinkSync(zip);

  // Enable site-packages so pip-installed packages (yfinance, scrapling) load.
  const pthFiles = fs.readdirSync(VENDOR_DIR).filter((f) => f.endsWith("._pth"));
  if (pthFiles.length === 0) {
    throw new Error(`No ._pth file found after extraction in ${VENDOR_DIR}`);
  }
  const pthFile = path.join(VENDOR_DIR, pthFiles[0]);
  let contents = fs.readFileSync(pthFile, "utf8");
  if (!/^\s*import site/m.test(contents)) {
    contents = contents.replace(/^#import site/m, "import site");
    fs.writeFileSync(pthFile, contents);
  }

  log("bootstrapping pip...");
  const pipScript = path.join(VENDOR_DIR, "get-pip.py");
  await download(GET_PIP_URL, pipScript);
  run(`"${PYTHON_EXE}" "${pipScript}" --no-warn-script-location`, { stdio: "inherit" });
  fs.unlinkSync(pipScript);

  log("installing yfinance (live prices)...");
  run(`"${PYTHON_EXE}" -m pip install --disable-pip-version-check --quiet yfinance`, { stdio: "inherit" });

  fs.writeFileSync(MARKER, `${VERSION}\n${new Date().toISOString()}\n`);
  log(`embedded Python ready at ${VENDOR_DIR}`);
}

(async () => {
  if (process.argv.includes("--check")) {
    process.exit(ready() ? 0 : 1);
  }
  try {
    await install();
  } catch (err) {
    console.error(`[py] failed: ${err.message || err}`);
    process.exit(1);
  }
})();
