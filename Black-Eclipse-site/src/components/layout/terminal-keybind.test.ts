import { describe, expect, it } from "vitest";
import { isTerminalShortcut } from "./terminal-keybind";
import { useTerminalStore, hydrateTerminalStore } from "@/lib/terminal/store";

function key(partial: Partial<KeyboardEvent>): Pick<KeyboardEvent, "ctrlKey" | "metaKey" | "code" | "key"> {
  return { ctrlKey: false, metaKey: false, code: "", key: "", ...partial };
}

describe("terminal toggle shortcut", () => {
  it("matches Ctrl+Backquote by code (layout-independent)", () => {
    expect(isTerminalShortcut(key({ ctrlKey: true, code: "Backquote", key: "`" }))).toBe(true);
  });

  it("matches Cmd+Backquote on macOS", () => {
    expect(isTerminalShortcut(key({ metaKey: true, code: "Backquote", key: "`" }))).toBe(true);
  });

  it("matches a layout that reports '~' instead of '`'", () => {
    expect(isTerminalShortcut(key({ ctrlKey: true, code: "Backquote", key: "~" }))).toBe(true);
  });

  it("falls back to the key when code is missing", () => {
    expect(isTerminalShortcut(key({ ctrlKey: true, key: "`" }))).toBe(true);
  });

  it("requires a modifier (a bare backquote is typing)", () => {
    expect(isTerminalShortcut(key({ code: "Backquote", key: "`" }))).toBe(false);
  });

  it("does not match other keys", () => {
    expect(isTerminalShortcut(key({ ctrlKey: true, code: "KeyT", key: "t" }))).toBe(false);
    expect(isTerminalShortcut(key({ ctrlKey: true, code: "Minus", key: "-" }))).toBe(false);
  });
});

describe("terminal store", () => {
  it("toggles and records the open state", () => {
    useTerminalStore.setState({ open: false, generation: 0 });
    useTerminalStore.getState().toggle();
    expect(useTerminalStore.getState().open).toBe(true);
    useTerminalStore.getState().toggle();
    expect(useTerminalStore.getState().open).toBe(false);
  });

  it("newShell opens and rotates the generation", () => {
    useTerminalStore.setState({ open: false, generation: 3 });
    useTerminalStore.getState().newShell();
    expect(useTerminalStore.getState().open).toBe(true);
    expect(useTerminalStore.getState().generation).toBe(4);
  });

  it("sets the placement and opens the panel, persisting the choice", () => {
    useTerminalStore.setState({ open: false, placement: "bottom" });
    useTerminalStore.getState().setPlacement("right");
    expect(useTerminalStore.getState().placement).toBe("right");
    expect(useTerminalStore.getState().open).toBe(true);
    // Persisted when a storage exists (browser); the state change is unconditional.
    if (typeof globalThis.localStorage !== "undefined") {
      expect(globalThis.localStorage.getItem("black-eclipse:terminal-placement")).toBe("right");
    }
    useTerminalStore.getState().setPlacement("full");
    expect(useTerminalStore.getState().placement).toBe("full");
  });

  it("hydrate is safe when there is nothing persisted", () => {
    expect(() => hydrateTerminalStore()).not.toThrow();
  });
});

describe("ordered input queue", () => {
  // A minimal extract of the drain contract: appended bytes are sent in order,
  // coalesced while a request is in flight, and never reordered. This is the
  // client half of the "typing arrived as terimnal" bug.
  function makeQueue(send: (batch: string) => Promise<void>) {
    let queue = "";
    let sending = false;
    const flush = async () => {
      if (sending) return;
      sending = true;
      try {
        while (queue) {
          const batch = queue;
          queue = "";
          await send(batch);
        }
      } finally {
        sending = false;
      }
    };
    return {
      push: (data: string) => {
        queue += data;
        return flush();
      },
      pending: () => queue,
    };
  }

  it("sends bytes in the exact order they were typed", async () => {
    const sent: string[] = [];
    const q = makeQueue(async (b) => { sent.push(b); });
    for (const ch of "terminal") await q.push(ch);
    expect(sent.join("")).toBe("terminal");
  });

  it("coalesces keystrokes typed during an in-flight request without reordering", async () => {
    const sent: string[] = [];
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => { release = r; });
    let first = true;
    const q = makeQueue(async (b) => {
      sent.push(b);
      if (first) { first = false; await gate; }
    });
    const p1 = q.push("ab");     // starts the request, blocks on the gate
    const p2 = q.push("cd");     // queued while in flight
    release();
    await Promise.all([p1, p2]);
    expect(sent.join("")).toBe("abcd");
  });
});
