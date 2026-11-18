import { afterEach, describe, expect, it, vi } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { COPY_EVENT, canCopyFromShell, copyText } from "./clipboard";

// Copy contract for the desktop shell.
//
// The bug this guards: the app's copy buttons used `navigator.clipboard`, which
// WebView2 answers with Chromium's permission bubble ("http://tauri.localhost
// wants to see text and images copied to the clipboard") drawn over the window —
// browser chrome inside a desktop app. Inside the shell, copy must go through the
// `be-copy` event and the native write.

// `src/` — this file lives at src/lib/desktop, so two levels up is the tree the
// source guard must walk.
const SRC = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..");

function installShell(bridge: "global" | "internals"): { events: Array<[string, unknown]> } {
  const events: Array<[string, unknown]> = [];
  const emit = (event: string, payload: unknown) => {
    events.push([event, payload]);
    return Promise.resolve();
  };
  const win: Record<string, unknown> = {};
  if (bridge === "global") {
    win.__TAURI__ = { event: { emit } };
  } else {
    win.__TAURI_INTERNALS__ = {
      invoke: (cmd: string, args: { event?: string; payload?: unknown }) => {
        events.push([cmd === "plugin:event|emit" ? String(args.event) : cmd, args.payload]);
        return Promise.resolve();
      },
    };
  }
  (globalThis as unknown as { window?: unknown }).window = win;
  return { events };
}

function installBrowserClipboard(writeText: () => Promise<void>) {
  Object.defineProperty(globalThis, "navigator", {
    value: { clipboard: { writeText } },
    configurable: true,
    writable: true,
  });
}

afterEach(() => {
  delete (globalThis as unknown as { window?: unknown }).window;
  Reflect.deleteProperty(globalThis, "navigator");
  vi.restoreAllMocks();
});

describe("copyText", () => {
  it("reports no shell bridge outside the desktop window", () => {
    expect(canCopyFromShell()).toBe(false);
  });

  it("sends the text over the be-copy event when the shell bridge is present", async () => {
    const { events } = installShell("global");
    const browser = vi.fn(async () => undefined);
    installBrowserClipboard(browser);

    await expect(copyText("line one\nline two")).resolves.toBe(true);

    expect(events).toEqual([[COPY_EVENT, { text: "line one\nline two" }]]);
    // The browser API must never be reached in the shell: that is what prompts.
    expect(browser).not.toHaveBeenCalled();
    expect(canCopyFromShell()).toBe(true);
  });

  it("falls back to the raw IPC emit when the global API is absent", async () => {
    const { events } = installShell("internals");
    await expect(copyText("symbol")).resolves.toBe(true);
    expect(events).toEqual([[COPY_EVENT, { text: "symbol" }]]);
  });

  it("uses the browser clipboard when there is no shell", async () => {
    const browser = vi.fn(async () => undefined);
    installBrowserClipboard(browser);

    await expect(copyText("plain")).resolves.toBe(true);
    expect(browser).toHaveBeenCalledWith("plain");
  });

  it("reports failure instead of claiming a copy that never happened", async () => {
    installBrowserClipboard(async () => {
      throw new Error("denied");
    });
    // No DOM in the test runtime, so the legacy selection path cannot rescue it.
    await expect(copyText("plain")).resolves.toBe(false);
  });
});

describe("desktop copy is the only clipboard path", () => {
  // Source guard: a new component calling `navigator.clipboard` would bring the
  // WebView2 permission bubble straight back. The helper owns every fallback.
  //
  // Scoped to the UI tree and the desktop helpers: those are where copy
  // affordances live, and reading every file in `src/` would add seconds to
  // every test run for no extra coverage.
  const WATCH = ["components", "app", join("lib", "desktop")];
  const ALLOWED = new Set(["lib/desktop/clipboard.ts"]);

  function walk(dir: string, out: string[] = []): string[] {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name === "generated") continue;
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full, out);
      else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\./.test(entry.name)) out.push(full);
    }
    return out;
  }

  it(
    "no component or desktop helper calls navigator.clipboard directly",
    () => {
      const files = WATCH.flatMap((dir) => walk(join(SRC, dir)));
      const offenders = files
        .filter((file) => !ALLOWED.has(relative(SRC, file).replaceAll("\\", "/")))
        .filter((file) => readFileSync(file, "utf8").includes("navigator.clipboard"))
        .map((file) => relative(SRC, file).replaceAll("\\", "/"));

      expect(offenders).toEqual([]);
    },
    60_000,
  );
});
