import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

// Architecture boundary guard (AGENTS.md: "Reuse before rebuild"; the app is
// layered app → components → lib → python runtime). Nothing enforced the
// direction of those imports, which is how `src/lib` grew a 209-file flat
// directory. This is the cheap, always-on version of an ESLint boundary config:
// it walks the real import graph and fails on a NEW upward dependency.
//
// The ratchet below is the debt that already existed when the guard landed.
// It may shrink; it must never grow. Fixing an entry is just deleting a line —
// a stale line is harmless, so removal is optional. Tests are exempt: a render
// test under `lib/` legitimately mounts a component.
//
// Relative specifiers are resolved to a real path, so `../../components/...`
// is caught exactly like `@/components/...`.

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SKIP = new Set(["generated", "node_modules", ".next", ".next-dev"]);

const KNOWN_UPWARD = new Set([
  // Dashboard widgets are TSX that compose the real chart/map/portfolio
  // components. The standing fix is to move the visual widgets into
  // `src/components/dashboard/`; until then they are frozen here.
  "lib/chat/use-context-picker.tsx -> components/workspace/file-source-picker",
  "lib/dashboard/chart-widgets.tsx -> components/chart/chart-widget",
  "lib/dashboard/chart-widgets.tsx -> components/screens/portfolio/use-echart",
  "lib/dashboard/heatmap-widget.tsx -> components/screens/portfolio/use-echart",
  "lib/dashboard/intelligence-widgets.tsx -> components/workspace/market-picker",
  "lib/dashboard/investor-eye-map-widget.tsx -> components/investor-eye/event-dossier-overlay",
  "lib/dashboard/investor-eye-map-widget.tsx -> components/investor-eye/heatmap-toggle",
  "lib/dashboard/investor-eye-map-widget.tsx -> components/investor-eye/layer-controller",
  "lib/dashboard/investor-eye-map-widget.tsx -> components/investor-eye/world-map",
  "lib/dashboard/market-rail-widgets.tsx -> components/workspace/market-picker",
  "lib/dashboard/portfolio-store.ts -> components/screens/portfolio/fund-store",
  "lib/dashboard/portfolio-store.ts -> components/screens/portfolio/use-live-quotes",
  "lib/dashboard/trading-widgets.tsx -> components/ui/select",
  "lib/dashboard/use-home-data.ts -> components/screens/portfolio/use-live-quotes",
  "lib/dashboard/widgets.tsx -> components/screens/earnings-calendar",
  "lib/dashboard/widgets.tsx -> components/screens/portfolio/use-echart",
  "lib/dashboard/widgets.tsx -> components/workspace/market-picker",
  "lib/news/saved.ts -> components/screens/market-news",
  "lib/notifications/bots-run-watcher.tsx -> components/screens/bots/bots-screen",
  // A UI type/config re-exported from the sidebar component. Standing fix:
  // define the type in `lib/sidebar/types.ts` and have the component import it.
  "lib/sidebar/config.ts -> components/layout/sidebar",
  "lib/sidebar/store.ts -> components/layout/sidebar",
  "lib/workspace/generic-charts.tsx -> components/screens/portfolio/use-echart",
  "lib/workspace/workspace-drawer.tsx -> components/ui/dialog",
]);

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith(".")) continue;
    const full = join(dir, e.name);
    if (e.isDirectory()) {
      if (SKIP.has(e.name)) continue;
      walk(full, out);
    } else if (/\.tsx?$/.test(e.name)) {
      out.push(full);
    }
  }
  return out;
}

const IMPORT_RE = /(?:from\s+|import\s*\(\s*|require\s*\(\s*)(['"])([^'"]+)\1/g;

/** Every specifier in a source file that points into `src/` or at a sibling. */
function internalImports(file: string): string[] {
  const text = readFileSync(file, "utf8");
  const out: string[] = [];
  for (const m of text.matchAll(IMPORT_RE)) {
    const spec = m[2];
    if (spec.startsWith(".")) out.push(resolve(dirname(file), spec));
    else if (spec.startsWith("@/")) out.push(resolve(SRC, spec.slice(2)));
  }
  return out;
}

const rel = (abs: string) => relative(SRC, abs).replace(/\\/g, "/");
const isInside = (target: string, dir: string) => {
  const r = relative(resolve(SRC, dir), target);
  return r !== "" && !r.startsWith("..") && !r.startsWith(sep) && !/^[A-Za-z]:/.test(r);
};
const isTest = (abs: string) => /\.test\.tsx?$/.test(abs);

describe("import boundaries (app → components → lib)", () => {
  const files = walk(SRC);

  it("src/lib does not add upward imports of UI or routes", () => {
    const violations: string[] = [];
    for (const file of files) {
      if (!isInside(file, "lib") || isTest(file)) continue;
      for (const target of internalImports(file)) {
        let dir: string | null = null;
        if (isInside(target, "components")) dir = "components";
        else if (isInside(target, "app")) dir = "app";
        if (!dir) continue;
        const edge = `${rel(file)} -> ${rel(target)}`;
        if (!KNOWN_UPWARD.has(edge)) violations.push(edge);
      }
    }
    expect(
      violations,
      `new upward imports from src/lib (move the UI down or add a justified ratchet line):\n${violations.join("\n")}`
    ).toEqual([]);
  });

  it("src/components never imports routes", () => {
    const violations: string[] = [];
    for (const file of files) {
      if (!isInside(file, "components")) continue;
      for (const target of internalImports(file)) {
        if (isInside(target, "app")) violations.push(`${rel(file)} -> ${rel(target)}`);
      }
    }
    expect(
      violations,
      `components must not import src/app (move the screen under src/components):\n${violations.join("\n")}`
    ).toEqual([]);
  });

  it("the walk is real", () => {
    expect(files.some((f) => f.endsWith(join("lib", "api-guard.ts")))).toBe(true);
  });
});
