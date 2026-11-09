import { describe, expect, it } from "vitest";
import {
  breadcrumbs,
  describeSource,
  folderOf,
  joinRelative,
  leafOf,
  originLabel,
  parentDir,
  searchFiles,
  type FileRef,
} from "./file-sources";

const files: FileRef[] = [
  { name: "chat-input.tsx", path: "src/components/chat/chat-input.tsx" },
  { name: "chat-dock.tsx", path: "src/components/chat/chat-dock.tsx" },
  { name: "messages.ts", path: "src/lib/chat/messages.ts" },
  { name: "README.md", path: "README.md" },
];

describe("path helpers", () => {
  it("splits folders and leaves", () => {
    expect(folderOf("src/a/b.ts")).toBe("src/a");
    expect(folderOf("README.md")).toBe("");
    expect(leafOf("src/a/b.ts")).toBe("b.ts");
    expect(leafOf("src/a/")).toBe("a");
  });

  it("builds and walks breadcrumbs", () => {
    expect(breadcrumbs("a/b/c")).toEqual(["a", "b", "c"]);
    expect(breadcrumbs(".")).toEqual([]);
    expect(parentDir("a/b/c")).toBe("a/b");
    expect(parentDir("a")).toBe("");
  });

  it("joins relative folders without a leading slash", () => {
    expect(joinRelative("a/b", "c.ts")).toBe("a/b/c.ts");
    expect(joinRelative(".", "c.ts")).toBe("c.ts");
    expect(joinRelative("", "c.ts")).toBe("c.ts");
  });
});

describe("provenance labels", () => {
  it("never pretends to know a local folder", () => {
    expect(originLabel("upload")).toBe("Local");
    expect(describeSource({ origin: "upload" }).toLowerCase()).toContain("local");
    expect(describeSource({ origin: "upload" }).toLowerCase()).toContain("uploaded copy");
  });

  it("shows the project root and folder", () => {
    expect(describeSource({
      origin: "project",
      sourcePath: "src/components/chat/chat-input.tsx",
      rootLabel: "black-eclipse",
    })).toBe("black-eclipse › src/components/chat");
  });

  it("labels pasted text", () => {
    expect(originLabel("paste")).toBe("Pasted");
    expect(describeSource({ origin: "paste" })).toBe("Pasted text");
  });
});

describe("file search", () => {
  it("prefers leaf-name matches over path matches", () => {
    const hits = searchFiles(files, "chat-dock");
    expect(hits[0].path).toBe("src/components/chat/chat-dock.tsx");
  });

  it("matches folder paths too", () => {
    const hits = searchFiles(files, "src/lib");
    expect(hits.map((h) => h.path)).toContain("src/lib/chat/messages.ts");
  });

  it("is deterministic and bounded", () => {
    const hits = searchFiles(files, "chat", 1);
    expect(hits).toHaveLength(1);
    expect(searchFiles(files, "chat", 1)).toEqual(hits);
  });

  it("returns nothing for a miss", () => {
    expect(searchFiles(files, "zzzzzz")).toEqual([]);
  });
});
