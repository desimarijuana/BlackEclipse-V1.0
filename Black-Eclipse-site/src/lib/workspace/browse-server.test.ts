import { afterEach, describe, expect, it } from "vitest";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { browseDirectory, createDirectory } from "./browse-server";

const made: string[] = [];

function tempDir(): string {
  const dir = mkdtempSync(path.join(tmpdir(), "be-browse-"));
  made.push(dir);
  return dir;
}

afterEach(() => {
  for (const dir of made.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("picker folder browsing (Node-native)", () => {
  it("lists directories first and includes files", () => {
    const root = tempDir();
    mkdirSync(path.join(root, "zeta"));
    writeFileSync(path.join(root, "a.txt"), "x");
    const result = browseDirectory(root);
    expect(result.path).toBe(root);
    expect(result.entries.map((e) => e.name)).toEqual(["zeta", "a.txt"]);
    expect(result.entries[0].isDir).toBe(true);
    expect(result.entries[1].isDir).toBe(false);
  });

  it("returns the drive roots when no path is given", () => {
    const result = browseDirectory(undefined);
    expect(result.path).toBeNull();
    expect(result.entries.length).toBeGreaterThan(0);
  });

  it("is honest about a missing folder", () => {
    const result = browseDirectory(path.join(tempDir(), "nope"));
    expect(result.entries).toEqual([]);
    expect(result.reason).toBeTruthy();
  });

  it("creates one leaf and is idempotent for an existing folder", () => {
    const root = tempDir();
    const created = createDirectory(root, "my project");
    expect(created.path).toBe(path.join(root, "my project"));
    expect(browseDirectory(root).entries.some((e) => e.name === "my project")).toBe(true);
    expect(createDirectory(root, "my project").name).toBe("my project");
  });

  it("refuses a path name, a missing parent, and a file collision", () => {
    const root = tempDir();
    for (const name of ["a/b", "a\\b", ".", "..", ""]) {
      expect(() => createDirectory(root, name)).toThrow();
    }
    expect(() => createDirectory(path.join(root, "missing"), "x")).toThrow();
    writeFileSync(path.join(root, "taken"), "x");
    expect(() => createDirectory(root, "taken")).toThrow();
  });
});
