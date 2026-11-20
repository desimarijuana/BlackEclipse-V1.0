import { beforeEach, describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();
vi.mock("@/lib/db", () => ({
  prisma: {
    systemConfig: {
      findUnique: async ({ where }: { where: { key: string } }) =>
        store.has(where.key) ? { key: where.key, value: store.get(where.key)! } : null,
      upsert: async ({
        where,
        create,
        update,
      }: {
        where: { key: string };
        create: { value: string };
        update: { value: string };
      }) => {
        store.set(where.key, (update?.value ?? create?.value) as string);
        return { key: where.key, value: store.get(where.key) };
      },
    },
  },
}));

const storedProviderKey = vi.fn(async (_envVar: string): Promise<string | null> => null);
vi.mock("@/lib/provider-keys", () => ({
  storedProviderKey: (envVar: string) => storedProviderKey(envVar),
}));

import {
  CUSTOM_CONNECTIONS_CONFIG_KEY,
  customConnectionKeyEnvVar,
  deleteCustomConnection,
  getCustomConnection,
  listCustomConnections,
  listCustomConnectionsPublic,
  saveCustomConnection,
} from "./custom-connections";

beforeEach(() => {
  store.clear();
  storedProviderKey.mockReset();
  storedProviderKey.mockResolvedValue(null);
});

describe("named custom connections", () => {
  it("creates a connection with a stable id and its own key env var", async () => {
    const created = await saveCustomConnection({
      name: "Company gateway",
      baseUrl: "https://llm.company.com/v1/",
      model: "m1",
      authStyle: "x-api-key",
    });
    expect(created.id).toMatch(/^company-gateway-/);
    expect(created.baseUrl).toBe("https://llm.company.com/v1");
    expect(created.authStyle).toBe("x-api-key");
    expect(customConnectionKeyEnvVar(created.id)).toMatch(/^CUSTOM_LLM_KEY_/);
    expect(JSON.parse(store.get(CUSTOM_CONNECTIONS_CONFIG_KEY)!)).toMatchObject({
      connections: [expect.objectContaining({ id: created.id })],
    });
  });

  it("edits in place and keeps the id (so the key is not orphaned)", async () => {
    const created = await saveCustomConnection({
      name: "Gateway",
      baseUrl: "https://one.example/v1",
      model: "m1",
      authStyle: "bearer",
    });
    const edited = await saveCustomConnection({
      id: created.id,
      name: "Gateway (prod)",
      baseUrl: "https://two.example/v1",
      model: "m2",
      authStyle: "api-key",
    });
    expect(edited.id).toBe(created.id);
    expect(edited.name).toBe("Gateway (prod)");
    expect(edited.baseUrl).toBe("https://two.example/v1");
    expect(edited.authStyle).toBe("api-key");
    expect(await listCustomConnections()).toHaveLength(1);
  });

  it("reports whether each connection has a key without exposing it", async () => {
    const created = await saveCustomConnection({
      name: "Gateway",
      baseUrl: "https://one.example/v1",
      model: "m1",
    });
    storedProviderKey.mockImplementation(async (envVar: string) =>
      envVar === customConnectionKeyEnvVar(created.id) ? "secret" : null,
    );
    const [row] = await listCustomConnectionsPublic();
    expect(row.hasKey).toBe(true);
    expect(JSON.stringify(row)).not.toContain("secret");
  });

  it("deletes the record", async () => {
    const created = await saveCustomConnection({
      name: "Gateway",
      baseUrl: "https://one.example/v1",
      model: "m1",
    });
    expect(await getCustomConnection(created.id)).not.toBeNull();
    await deleteCustomConnection(created.id);
    expect(await getCustomConnection(created.id)).toBeNull();
  });
});
