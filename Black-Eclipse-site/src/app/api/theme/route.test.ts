import { describe, it, expect, vi, beforeEach } from "vitest";
import { DEFAULT_ECLIPSE_THEME } from "@/lib/theme/tokens";

// Front-door contract for /api/theme — the APP-WIDE Eclipse theme. It is a
// mutation surface (PUT/DELETE), so it must be operator-gated and must service
// the GET read without touching the DB mock's shape.

const getServerThemeState = vi.fn(async () => ({ theme: null, initialized: false }));
const setServerTheme = vi.fn(async (_raw: unknown) => DEFAULT_ECLIPSE_THEME);
const clearServerTheme = vi.fn(async () => undefined);

vi.mock("@/lib/theme/server", () => ({
  getServerThemeState: () => getServerThemeState(),
  setServerTheme: (raw: unknown) => setServerTheme(raw),
  clearServerTheme: () => clearServerTheme(),
}));

import { GET, PUT, DELETE } from "@/app/api/theme/route";

function mutate(method: string, body?: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/theme", {
    method,
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

beforeEach(() => {
  getServerThemeState.mockClear();
  setServerTheme.mockClear();
  clearServerTheme.mockClear();
});

describe("GET /api/theme", () => {
  it("returns the app-wide theme state (null + uninitialized when unset)", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ theme: null, initialized: false });
  });
});

describe("PUT /api/theme", () => {
  it("refuses a cross-origin mutation before writing", async () => {
    const res = await PUT(mutate("PUT", { theme: DEFAULT_ECLIPSE_THEME }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(setServerTheme).not.toHaveBeenCalled();
  });

  it("saves the theme and echoes it back", async () => {
    const res = await PUT(mutate("PUT", { theme: DEFAULT_ECLIPSE_THEME }));
    expect(res.status).toBe(200);
    expect(setServerTheme).toHaveBeenCalledWith(DEFAULT_ECLIPSE_THEME);
    expect((await res.json()).success).toBe(true);
  });
});

describe("DELETE /api/theme", () => {
  it("clears the app-wide theme", async () => {
    const res = await DELETE(mutate("DELETE"));
    expect(res.status).toBe(200);
    expect(clearServerTheme).toHaveBeenCalled();
  });
});
