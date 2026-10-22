#!/usr/bin/env node
/*
 * Regenerate the PORTABLE tool manifest.
 *
 * Round 3 / W10 (ADR-H298). `docs/harness/tool-registry.json` is the tool
 * surface other harnesses can consume: every publishable tool, with its
 * PERMISSION and its EFFECT CLASS. A consumer inherits Eclipse's honesty - it
 * can see that a tool writes, or that it reaches the network, before it binds
 * it - and a tool whose effect cannot be classified is NOT published at all.
 *
 * The file is GENERATED. A test regenerates it and compares, so the manifest
 * cannot drift away from the registry that actually exists.
 *
 * Usage: node scripts/generate-tool-registry.js
 */

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const site = path.resolve(__dirname, "..");
const pythonDir = path.join(site, "python");

function interpreter() {
  const vendored = path.join(site, "scripts", "vendor", "python", "python.exe");
  if (fs.existsSync(vendored)) return vendored;
  return process.platform === "win32" ? "python" : "python3";
}

const NL = "chr(10)";
const driver = path.join(os.tmpdir(), `eclipse-tool-registry-${process.pid}.py`);
fs.writeFileSync(
  driver,
  [
    "import json, os, sys",
    `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
    "from harness.public import tool_manifest",
    "manifest = tool_manifest()",
    "target = os.path.join(os.getcwd(), 'docs', 'harness', 'tool-registry.json')",
    "os.makedirs(os.path.dirname(target), exist_ok=True)",
    "with open(target, 'w', encoding='utf-8', newline='') as handle:",
    "    json.dump(manifest, handle, indent=2, sort_keys=True, ensure_ascii=False)",
    `    handle.write(${NL})`,
    "print('wrote', target, '-', manifest['toolCount'], 'tools, digest', manifest['digest'])",
    "",
  ].join("\n"),
  "utf8",
);

try {
  const result = spawnSync(interpreter(), [driver], { stdio: "inherit", cwd: site });
  process.exit(result.status ?? 1);
} finally {
  try { fs.unlinkSync(driver); } catch (_) { /* best effort */ }
}
