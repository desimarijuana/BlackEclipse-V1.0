// postinstall: install Python yfinance bridge deps if Python is available.
// Skips silently when Python is missing (app runs fine without live prices).
const { execSync } = require("child_process");

const candidates = process.platform === "win32" ? ["python", "python3", "py"] : ["python3", "python"];

for (const cmd of candidates) {
  try {
    execSync(`${cmd} --version`, { stdio: "ignore" });
  } catch {
    continue;
  }
  try {
    execSync(`${cmd} -c "import yfinance"`, { stdio: "ignore", timeout: 15000 });
    console.log("[setup] Python yfinance bridge already installed.");
  } catch {
    console.log("[setup] Installing Python deps (yfinance) for live prices...");
    try {
      execSync(`${cmd} -m pip install yfinance`, { stdio: "inherit" });
      console.log("[setup] Python deps installed.");
    } catch {
      console.warn("[setup] Could not install yfinance automatically. Live prices disabled; install manually with:");
      console.warn(`         ${cmd} -m pip install yfinance`);
    }
  }
  process.exit(0);
}
console.log("[setup] Python not found — live price refresh disabled (app works, prices stay static).");
console.log("        Install Python 3 from https://python.org, then: pip install yfinance");