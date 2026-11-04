import { describe, expect, it } from "vitest";
import {
  assertModelAllowed,
  localModelsOnly,
  privacyMode,
  PrivacyViolationError,
} from "./privacy";

const LOCAL = "http://127.0.0.1:11434/v1";
const CLOUD = "https://api.openai.com/v1";

describe("privacy mode", () => {
  it("is off by default", () => {
    expect(privacyMode({})).toBe("off");
    expect(localModelsOnly({})).toBe(false);
    expect(() => assertModelAllowed(CLOUD, "openai", {})).not.toThrow();
  });

  it("accepts every documented spelling of the local-only mode", () => {
    for (const value of ["local-models", "LOCAL_MODELS", "local-only", " local ", "no-cloud"]) {
      expect(privacyMode({ ECLIPSE_PRIVACY: value })).toBe("local-models");
    }
    for (const value of ["", "off", "anything-else"]) {
      expect(privacyMode({ ECLIPSE_PRIVACY: value })).toBe("off");
    }
  });

  it("blocks a remote provider before any request is sent", () => {
    const env = { ECLIPSE_PRIVACY: "local-models" };
    expect(() => assertModelAllowed(CLOUD, "openai", env)).toThrow(PrivacyViolationError);
    expect(() => assertModelAllowed(CLOUD, "openai", env)).toThrow(/local-models/i);
    expect(() => assertModelAllowed(undefined, "anthropic", env)).toThrow(PrivacyViolationError);
  });

  it("allows loopback providers and the offline mock provider", () => {
    const env = { ECLIPSE_PRIVACY: "local-models" };
    expect(() => assertModelAllowed(LOCAL, "ollama", env)).not.toThrow();
    expect(() => assertModelAllowed("http://localhost:1234/v1", "lmstudio", env)).not.toThrow();
    expect(() => assertModelAllowed(CLOUD, "mock", env)).not.toThrow();
  });

  it("does not mistake a remote hostname for loopback", () => {
    const env = { ECLIPSE_PRIVACY: "local-models" };
    expect(() => assertModelAllowed("http://localhost.evil.example/v1", "custom", env)).toThrow();
    expect(() => assertModelAllowed("https://10.0.0.5/v1", "custom", env)).toThrow();
  });
});
