// postinstall: install Python yfinance bridge deps if Python is available.
// On Windows, auto-provisions a vendored embedded Python when none exists so
// live prices work out of the box for new users.
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const vendored = path.join(__dirname, "vendor", "python", "python.exe");
const candidates =
  process.platform === "win32"
    ? [fs.existsSync(vendored) ? vendored : null, "python", "python3", "py"].filter(Boolean)
    : ["python3", "python"];

for (const cmd of candidates) {
  try {
    execSync(`"${cmd}" --version`, { stdio: "ignore" });
  } catch {
    continue;
  }
  try {
    execSync(`"${cmd}" -c "import yfinance"`, { stdio: "ignore", timeout: 15000 });
    console.log("[setup] Python yfinance bridge already installed.");
  } catch {
    console.log("[setup] Installing Python deps (yfinance) for live prices...");
    try {
      execSync(`"${cmd}" -m pip install yfinance`, { stdio: "inherit" });
      console.log("[setup] Python deps installed.");
    } catch {
      console.warn("[setup] Could not install yfinance automatically. Live prices disabled; install manually with:");
      console.warn(`         ${cmd} -m pip install yfinance`);
    }
  }
  process.exit(0);
}
console.log("[setup] Python not found — provisioning embedded Python...");
try {
  execSync(`node "${path.join(__dirname, "setup-embedded-python.js")}"`, { stdio: "inherit" });
} catch {
  console.log("        Install Python 3 from https://python.org, then: pip install yfinance");
}