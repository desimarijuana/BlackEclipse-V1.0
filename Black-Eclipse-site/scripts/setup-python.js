// postinstall: install Python deps if Python is available.
// Two dependency sets:
//   1. yfinance bridge deps (live prices)
//   2. the harness agent runtime (FastAPI + LangChain + LangGraph)
// On Windows, auto-provisions a vendored embedded Python when none exists so
// the app works out of the box for new users.
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const vendored = path.join(__dirname, "vendor", "python", "python.exe");
const requirements = path.join(__dirname, "..", "python", "requirements.txt");
const analysisRequirements = path.join(__dirname, "..", "python", "analysis-requirements.txt");

// The SANDBOX runs in the vendored interpreter (`interpreter_path()` resolves
// `scripts/vendor/python/python.exe`), never in whatever Python happens to be
// on PATH. So on Windows the vendored one is provisioned FIRST and used for
// every install — a system Python cannot serve the sandbox.
if (process.platform === "win32" && !fs.existsSync(vendored)) {
  console.log("[setup] Provisioning the vendored Python the sandbox runs in...");
  try {
    execSync(`node "${path.join(__dirname, "setup-embedded-python.js")}"`, { stdio: "inherit" });
  } catch {
    console.warn("[setup] Could not provision the vendored Python. The analysis sandbox");
    console.warn("         will report SANDBOX_UNAVAILABLE until it exists.");
  }
}

const candidates =
  process.platform === "win32"
    ? [fs.existsSync(vendored) ? vendored : null, "python", "python3", "py"].filter(Boolean)
    : ["python3", "python"];

function hasModule(cmd, module, timeout = 20000) {
  try {
    execSync(`"${cmd}" -c "import ${module}"`, { stdio: "ignore", timeout });
    return true;
  } catch {
    return false;
  }
}

for (const cmd of candidates) {
  try {
    execSync(`"${cmd}" --version`, { stdio: "ignore" });
  } catch {
    continue;
  }

  // 1. yfinance bridge.
  if (hasModule(cmd, "yfinance")) {
    console.log("[setup] Python yfinance bridge already installed.");
  } else {
    console.log("[setup] Installing Python deps (yfinance) for live prices...");
    try {
      execSync(`"${cmd}" -m pip install yfinance`, { stdio: "inherit" });
    } catch {
      console.warn("[setup] Could not install yfinance. Live prices disabled; install manually with:");
      console.warn(`         ${cmd} -m pip install yfinance`);
    }
  }

  // 2. Harness agent runtime (FastAPI + LangChain + LangGraph).
  //    langgraph is the marker: if it imports, the runtime stack is present.
  if (hasModule(cmd, "langgraph")) {
    console.log("[setup] Python agent runtime already installed.");
  } else {
    console.log("[setup] Installing Python agent runtime (LangChain + LangGraph)...");
    try {
      execSync(`"${cmd}" -m pip install -r "${requirements}" --disable-pip-version-check`, {
        stdio: "inherit",
        timeout: 600000,
      });
      console.log("[setup] Python agent runtime installed.");
    } catch {
      console.warn("[setup] Could not install the agent runtime. The agentic harness will be");
      console.warn("         unavailable until you run:");
      console.warn(`         ${cmd} -m pip install -r python/requirements.txt`);
    }
  }

  // 3. The SANDBOX's numerical stack (numpy, pandas, matplotlib). This is the
  //    environment an `analysis_run` program executes in, so it must live in
  //    the SAME interpreter the sandbox runs (the vendored one on Windows).
  if (hasModule(cmd, "numpy") && hasModule(cmd, "pandas") && hasModule(cmd, "matplotlib")) {
    console.log("[setup] Python analysis stack already installed.");
  } else {
    console.log("[setup] Installing the analysis stack (numpy, pandas, matplotlib)...");
    try {
      execSync(`"${cmd}" -m pip install -r "${analysisRequirements}" --disable-pip-version-check`, {
        stdio: "inherit",
        timeout: 600000,
      });
      console.log("[setup] Python analysis stack installed.");
    } catch {
      console.warn("[setup] Could not install the analysis stack. The sandbox can still run,");
      console.warn("         but a computation that needs numpy/pandas/matplotlib will fail");
      console.warn("         honestly. Install later with:");
      console.warn(`         ${cmd} -m pip install -r python/analysis-requirements.txt`);
    }
  }

  // 4. Computer Use Engine backends (Pillow capture, Windows UIA + OCR). OPTIONAL
  //    in effect: a missing one degrades to an honest UNAVAILABLE, but installing
  //    it by default makes the desktop toolset fully functional out of the box.
  //    The `-r requirements.txt` install above already includes these (with
  //    platform markers), so only repair them explicitly if the runtime marker
  //    landed but the extras did not.
  if (hasModule(cmd, "PIL") && (process.platform !== "win32" || hasModule(cmd, "uiautomation"))) {
    console.log("[setup] Computer-use backends already installed.");
  } else {
    console.log("[setup] Installing computer-use backends (Pillow, and Windows UIA/OCR)...");
    try {
      const extras = ["Pillow"];
      if (process.platform === "win32") extras.push("uiautomation", "winsdk");
      execSync(`"${cmd}" -m pip install ${extras.join(" ")} --disable-pip-version-check`, {
        stdio: "inherit",
        timeout: 300000,
      });
    } catch {
      console.warn("[setup] Could not install optional computer-use backends. Desktop");
      console.warn("         tools stay available with honest fallbacks (OCR/accessibility may");
      console.warn("         report unavailable). Install later with:");
      console.warn(`         ${cmd} -m pip install Pillow${process.platform === "win32" ? " uiautomation winsdk" : ""}`);
    }
  }
  process.exit(0);
}
console.log("[setup] Python not found — provisioning embedded Python...");
try {
  execSync(`node "${path.join(__dirname, "setup-embedded-python.js")}"`, { stdio: "inherit" });
} catch {
  console.log("        Install Python 3 from https://python.org, then:");
  console.log("        pip install yfinance");
  console.log("        pip install -r python/requirements.txt");
}
