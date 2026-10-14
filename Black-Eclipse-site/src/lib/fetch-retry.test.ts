import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchWithRetry, isTransientFetchError } from "./fetch-retry";

// Pin the retry contract: transport failures retry with backoff, everything
// else (HTTP statuses, aborts, programming errors) must pass through untouched.

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

function networkError(): TypeError {
  return new TypeError("Failed to fetch");
}

describe("isTransientFetchError", () => {
  it("recognizes Failed to fetch / network errors", () => {
    expect(isTransientFetchError(networkError())).toBe(true);
    expect(isTransientFetchError(new TypeError("NetworkError when attempting to fetch resource."))).toBe(true);
    expect(isTransientFetchError(new TypeError("Load failed"))).toBe(true);
  });

  it("rejects aborts, HTTP errors and plain errors", () => {
    const abort = new Error("The user aborted a request.");
    abort.name = "AbortError";
    expect(isTransientFetchError(abort)).toBe(false);
    expect(isTransientFetchError(new Error("boom"))).toBe(false);
    expect(isTransientFetchError("Failed to fetch")).toBe(false);
    expect(isTransientFetchError(undefined)).toBe(false);
  });
});

describe("fetchWithRetry", () => {
  it("retries a transport failure then returns the response", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(networkError())
      .mockResolvedValueOnce(new Response("ok", { status: 200 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await fetchWithRetry("/api/stocks", undefined, { backoffMs: 1 });
    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gives up after the configured attempts and rethrows", async () => {
    const fetchMock = vi.fn().mockRejectedValue(networkError());
    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(fetchWithRetry("/api/stocks", undefined, { retries: 1, backoffMs: 1 })).rejects.toThrow("Failed to fetch");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry non-transport errors", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("serialization bug"));
    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(fetchWithRetry("/api/stocks", undefined, { backoffMs: 1 })).rejects.toThrow("serialization bug");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not retry once the caller's signal is aborted", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockImplementation(async () => {
      controller.abort();
      throw networkError();
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(fetchWithRetry("/api/stocks", { signal: controller.signal }, { backoffMs: 1 })).rejects.toThrow("Failed to fetch");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("returns HTTP error responses without retrying", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("nope", { status: 500 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await fetchWithRetry("/api/stocks", undefined, { backoffMs: 1 });
    expect(res.status).toBe(500);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
