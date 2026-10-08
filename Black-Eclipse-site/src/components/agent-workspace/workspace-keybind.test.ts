import { describe, expect, it } from "vitest";
import { isWorkspaceShortcut } from "./workspace-keybind";
import { useWorkspaceStore } from "@/lib/agent-workspace/store";

function key(
  partial: Partial<KeyboardEvent>,
): Pick<KeyboardEvent, "ctrlKey" | "metaKey" | "shiftKey" | "altKey" | "code" | "key"> {
  return { ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, code: "", key: "", ...partial };
}

describe("agent workspace toggle shortcut", () => {
  it("matches Ctrl+Shift+E by code (layout-independent)", () => {
    expect(isWorkspaceShortcut(key({ ctrlKey: true, shiftKey: true, code: "KeyE", key: "E" }))).toBe(true);
  });

  it("matches Cmd+Shift+E on macOS", () => {
    expect(isWorkspaceShortcut(key({ metaKey: true, shiftKey: true, code: "KeyE", key: "E" }))).toBe(true);
  });

  it("falls back to the key when code is missing", () => {
    expect(isWorkspaceShortcut(key({ ctrlKey: true, shiftKey: true, key: "E" }))).toBe(true);
  });

  it("requires shift and a modifier", () => {
    expect(isWorkspaceShortcut(key({ ctrlKey: true, code: "KeyE", key: "e" }))).toBe(false);
    expect(isWorkspaceShortcut(key({ shiftKey: true, code: "KeyE", key: "E" }))).toBe(false);
    expect(isWorkspaceShortcut(key({ code: "KeyE", key: "e" }))).toBe(false);
  });

  it("rejects chords carrying Alt or both primaries", () => {
    expect(isWorkspaceShortcut(key({ ctrlKey: true, shiftKey: true, altKey: true, code: "KeyE" }))).toBe(false);
    expect(isWorkspaceShortcut(key({ ctrlKey: true, metaKey: true, shiftKey: true, code: "KeyE" }))).toBe(false);
  });

  it("does not match other keys", () => {
    expect(isWorkspaceShortcut(key({ ctrlKey: true, shiftKey: true, code: "KeyD", key: "D" }))).toBe(false);
    expect(isWorkspaceShortcut(key({ ctrlKey: true, shiftKey: true, code: "KeyE", key: "e" }))).toBe(true);
  });
});

describe("agent workspace store toggle", () => {
  it("toggles open and closed", () => {
    useWorkspaceStore.setState({ open: false });
    useWorkspaceStore.getState().toggle();
    expect(useWorkspaceStore.getState().open).toBe(true);
    useWorkspaceStore.getState().toggle();
    expect(useWorkspaceStore.getState().open).toBe(false);
  });
});
