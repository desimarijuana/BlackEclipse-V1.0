import { describe, it, expect } from "vitest";
import { LLM_PRESETS, getLLMPreset, presetForBaseUrl, isLocalBaseUrl, CATALOG_ENV_VARS } from "./presets";

describe("LLM presets", () => {
  it("every preset has a usable OpenAI-compatible base URL", () => {
    for (const preset of LLM_PRESETS) {
      expect(() => new URL(preset.baseUrl)).not.toThrow();
      expect(preset.baseUrl.endsWith("/")).toBe(false);
      expect(preset.name.length).toBeGreaterThan(0);
      expect(preset.description.length).toBeGreaterThan(0);
      expect(preset.model.length).toBeGreaterThan(0);
    }
  });

  it("every remote preset declares the env var that supplies its key", () => {
    for (const preset of LLM_PRESETS) {
      if (preset.id === "custom" || preset.keyless) continue;
      expect(preset.envVar, `${preset.id} must declare envVar`).toBeTruthy();
    }
  });

  it("local presets are keyless and point at localhost", () => {
    for (const preset of LLM_PRESETS.filter((p) => p.keyless && p.id !== "custom")) {
      expect(isLocalBaseUrl(preset.baseUrl)).toBe(true);
    }
  });

  it("has no duplicate ids or base URLs", () => {
    expect(new Set(LLM_PRESETS.map((p) => p.id)).size).toBe(LLM_PRESETS.length);
    const urls = LLM_PRESETS.filter((p) => p.id !== "custom").map((p) => p.baseUrl);
    expect(new Set(urls).size).toBe(urls.length);
  });

  it("looks up by id and matches a saved base URL", () => {
    expect(getLLMPreset("groq")?.name).toBe("Groq");
    expect(getLLMPreset("nope")).toBeUndefined();
    expect(presetForBaseUrl("https://api.groq.com/openai/v1/")?.id).toBe("groq");
    expect(presetForBaseUrl("https://unknown.example.com/v1")).toBeUndefined();
  });

  it("covers a useful spread of providers", () => {
    const ids = LLM_PRESETS.map((p) => p.id);
    for (const expected of ["openai", "anthropic", "ollama", "groq", "gemini", "openrouter", "custom"]) {
      // `gemini` is the Google preset's id.
      if (expected === "gemini") expect(ids).toContain("google");
      else expect(ids).toContain(expected);
    }
  });
});

describe("isLocalBaseUrl", () => {
  it("recognises local hosts", () => {
    expect(isLocalBaseUrl("http://localhost:11434/v1")).toBe(true);
    expect(isLocalBaseUrl("http://127.0.0.1:1234/v1")).toBe(true);
    expect(isLocalBaseUrl("http://[::1]:8080/v1")).toBe(true);
  });

  it("rejects remote hosts and malformed URLs", () => {
    expect(isLocalBaseUrl("https://api.openai.com/v1")).toBe(false);
    expect(isLocalBaseUrl("not a url")).toBe(false);
  });
});

describe("CATALOG_ENV_VARS", () => {
  it("lists every env var the UI reports, with no duplicates", () => {
    expect(new Set(CATALOG_ENV_VARS).size).toBe(CATALOG_ENV_VARS.length);
    expect(CATALOG_ENV_VARS.length).toBeGreaterThan(15);
  });

  it("includes every remote preset key", () => {
    for (const preset of LLM_PRESETS) {
      if (preset.envVar) expect(CATALOG_ENV_VARS).toContain(preset.envVar);
    }
  });
});
