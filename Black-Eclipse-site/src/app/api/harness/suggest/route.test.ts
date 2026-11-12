import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/harness/clients/skills-client", () => ({
  listSkills: vi.fn(async () => ({
    skills: [
      { id: "crypto-onchain-research", name: "Crypto on-chain research", description: "Token flows", category: "research" },
      { id: "risk-review", name: "Risk review", description: "Portfolio concentration", category: "finance" },
    ],
  })),
}));

vi.mock("@/lib/harness/clients/portfolio-client", () => ({
  listPortfolios: vi.fn(async () => [
    { id: "pf_1", name: "Core fund", baseCurrency: "USD", description: null },
  ]),
}));

vi.mock("@/lib/harness/clients/workflows-client", () => ({
  listWorkflows: vi.fn(async () => [
    { id: "wf_1", version: "1", name: "Morning routine", description: null, createdAt: "" },
  ]),
}));

vi.mock("@/lib/harness/clients/python-client", () => ({
  listModelProviders: vi.fn(async () => [
    { id: "openai", label: "OpenAI", models: ["gpt-5", "gpt-5-mini"] },
  ]),
}));

vi.mock("@/lib/search/registry", () => ({
  getAllInstruments: vi.fn(() => [
    { symbol: "AAPL", title: "Apple Inc." },
    { symbol: "BTC", title: "Bitcoin" },
  ]),
}));

import { GET } from "./route";

function request(query: string): Request {
  return new Request(`http://localhost/api/harness/suggest?${query}`);
}

describe("GET /api/harness/suggest", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rejects an unknown provider", async () => {
    const res = await GET(request("provider=nope&q=x"));
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ candidates: [], error: "unknown provider" });
  });

  it("filters and maps skills", async () => {
    const res = await GET(request("provider=skills&q=crypto"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      candidates: [
        { value: "crypto-onchain-research", label: "Crypto on-chain research", subtitle: "Token flows" },
      ],
    });
  });

  it("suggests symbols from the static instrument registry", async () => {
    const res = await GET(request("provider=symbols&q=aa"));
    expect(await res.json()).toEqual({
      candidates: [{ value: "AAPL", label: "AAPL", subtitle: "Apple Inc." }],
    });
  });

  it("maps portfolios, workflows and models", async () => {
    expect(await (await GET(request("provider=portfolios&q=core"))).json()).toEqual({
      candidates: [{ value: "pf_1", label: "Core fund", subtitle: "USD" }],
    });
    expect(await (await GET(request("provider=workflows&q=morning"))).json()).toEqual({
      candidates: [{ value: "wf_1", label: "Morning routine", subtitle: undefined }],
    });
    expect(await (await GET(request("provider=models&q=openai"))).json()).toEqual({
      candidates: [{ value: "openai", label: "OpenAI", subtitle: "2 models" }],
    });
  });

  it("degrades to an empty list when a provider is unavailable", async () => {
    const { listSkills } = await import("@/lib/harness/clients/skills-client");
    vi.mocked(listSkills).mockRejectedValueOnce(new Error("runtime down"));
    const res = await GET(request("provider=skills&q=crypto"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ candidates: [], unavailable: true });
  });
});
