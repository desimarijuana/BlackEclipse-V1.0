// Browser-level drift UI smoke: bundle the real components, mock only fetch, and
// exercise the operator path in Chromium. No app server or Python runtime needed.
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import * as esbuild from "esbuild";
import { chromium } from "playwright";

const root = process.cwd();
const out = await mkdtemp(path.join(tmpdir(), "be-drift-ui-"));
const bundlePath = path.join(out, "bundle.js");
const htmlPath = path.join(out, "index.html");
let browser;

try {
  await esbuild.build({
    entryPoints: [path.join(root, "scripts/fixtures/drift-ui-entry.tsx")],
    bundle: true,
    outfile: bundlePath,
    platform: "browser",
    format: "iife",
    jsx: "automatic",
    define: { "process.env.NODE_ENV": '"production"' },
    absWorkingDir: root,
    logLevel: "silent",
  });
  await writeFile(htmlPath, [
    "<!doctype html><html><body><div id=\"root\"></div>",
    `<script src="${pathToFileURL(bundlePath).href}"></script>`,
    "</body></html>",
  ].join(""));

  browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  await page.goto(pathToFileURL(htmlPath).href);

  await page.getByText("Production drift").waitFor();
  await page.getByRole("button", { name: /eclipse-agent/ }).click();
  await page.getByRole("button", { name: /Open drift candidate/i }).click();
  await page.getByText(/Candidate scope: global/).waitFor();
  await page.getByRole("button", { name: /View evidence/i }).first().click();
  await page.getByText(/inert \| eclipse-agent/).waitFor();

  const selected = await page.locator("select").first().inputValue();
  if (selected !== "eclipse-agent") {
    throw new Error(`scope selection did not propagate: ${selected}`);
  }
  if (errors.length > 0) {
    throw new Error(`page errors: ${errors.join("; ")}`);
  }
  console.log("drift UI smoke: PASS (scope chip, candidate, evidence jump)");
} finally {
  await browser?.close();
  await rm(out, { recursive: true, force: true });
}
