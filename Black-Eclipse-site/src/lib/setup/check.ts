// ── Readiness checks (server-only) ──────────────────────────────────────────
// "Run a quick check" must report what actually happened. A stored key with a
// rejected request is `failed`, never `ok`. Included open sources are reported
// as `ok` because they need no account; that is not a reachability claim.
//
// Every network probe has a hard timeout and is bounded. The caller rate-limits
// the route, so this module never spins in the background.

import { getLLMConfig, setConfig, LOCAL_KEY_SENTINEL } from "@/lib/settings";
import { isLocalBaseUrl, resolveLLMProviderId } from "@/lib/agent/presets";
import { testConnection } from "@/lib/agent/connection";
import { providerKeyDef, resolveProviderKey } from "@/lib/provider-keys";
import { SOURCE_BY_ID } from "./source-catalog";
import { INCLUDED_PROBES } from "./included-probes";
import { effectiveSourcePreferences } from "./state";
import type { SourceId } from "./types";

export type CheckStatus = "ok" | "failed" | "rate-limited" | "unavailable" | "skipped";

export interface CheckItem {
  id: string;
  label: string;
  kind: "ai" | "source" | "key";
  status: CheckStatus;
  message: string;
  latencyMs?: number;
  httpStatus?: number;
}

function timeout(ms: number): AbortSignal {
  return AbortSignal.timeout(ms);
}

async function testIncludedSource(id: SourceId): Promise<CheckItem> {
  const def = SOURCE_BY_ID[id];
  const label = def?.label ?? id;
  const probe = INCLUDED_PROBES[id];
  if (!probe) {
    return {
      id, label, kind: "source", status: "unavailable",
      message: "No reachability probe is declared for this included source.",
    };
  }

  const started = Date.now();
  try {
    const res = await fetch(probe.url, {
      method: "GET",
      headers: probe.headers,
      redirect: "follow",
      signal: timeout(12_000),
    });
    const latencyMs = Date.now() - started;
    if (res.ok) {
      return {
        id, label, kind: "source", status: "ok",
        message: "Reachable — included open data, no account required.",
        latencyMs, httpStatus: res.status,
      };
    }
    return {
      id, label, kind: "source",
      status: res.status === 429 ? "rate-limited" : "failed",
      message: `Endpoint answered HTTP ${res.status}.`,
      latencyMs, httpStatus: res.status,
    };
  } catch (err) {
    return {
      id, label, kind: "source", status: "failed",
      message: err instanceof Error ? `Could not reach endpoint: ${err.message}` : "Probe failed",
      latencyMs: Date.now() - started,
    };
  }
}

export interface AiCheckOverride {
  providerId?: string;
  baseUrl?: string;
  model?: string;
  apiKey?: string;
}

async function testAi(override?: AiCheckOverride): Promise<CheckItem> {
  const saved = await getLLMConfig();
  const baseUrl = (override?.baseUrl || saved.baseUrl).replace(/\/$/, "");
  const model = override?.model || saved.model;
  const local = isLocalBaseUrl(baseUrl);

  const rawKey = override?.apiKey ?? saved.apiKey;
  const apiKey = rawKey === LOCAL_KEY_SENTINEL ? "" : rawKey;

  // A `mock` sentinel with a saved local endpoint is a working chat setup (the
  // runtime resolves it to the keyless local provider); only a sentinel with no
  // usable endpoint is genuinely unconfigured.
  const noModel = !override && saved.provider === "mock" && !local;
  if (noModel || (!apiKey && !local)) {
    return {
      id: "ai",
      label: "Chat model",
      kind: "ai",
      status: "skipped",
      message: noModel
        ? "No model configured — Chat will be unavailable."
        : "No API key configured — Chat will be unavailable.",
    };
  }

  const providerId =
    override?.providerId ??
    resolveLLMProviderId({ provider: override ? "custom" : saved.provider, baseUrl });

  // Auth-aware and protocol-aware: OpenAI gets Bearer, Anthropic gets
  // `x-api-key`, Gemini gets `x-goog-api-key`. The old hard-coded Bearer probe
  // reported valid Claude/Gemini keys as rejected.
  const result = await testConnection({
    providerId,
    baseUrl,
    model,
    apiKey,
    verifyChat: true,
  });

  if (result.ok) {
    return {
      id: "ai",
      label: "Chat model",
      kind: "ai",
      status: "ok",
      message: `${override ? "Custom endpoint" : providerId} · ${model}`,
      latencyMs: result.latencyMs,
      httpStatus: result.httpStatus,
    };
  }
  return {
    id: "ai",
    label: "Chat model",
    kind: "ai",
    status: result.code === "RATE_LIMITED" ? "rate-limited" : "failed",
    message: result.message,
    latencyMs: result.latencyMs,
    httpStatus: result.httpStatus,
  };
}

async function testKeyedSource(id: SourceId): Promise<CheckItem> {
  const def = SOURCE_BY_ID[id];
  const label = def?.label ?? id;
  const envVar = def?.envVar;
  if (!envVar || !def) {
    return { id, label, kind: "source", status: "unavailable", message: "No credential mapping." };
  }

  const keyDef = providerKeyDef(envVar);
  if (!keyDef) {
    return { id, label, kind: "source", status: "unavailable", message: "Unknown provider key." };
  }

  const key = await resolveProviderKey(envVar);
  if (!key) {
    return {
      id, label, kind: "source", status: "skipped",
      message: "No key connected — this capability will show UNAVAILABLE.",
    };
  }
  if (!keyDef.test) {
    return { id, label, kind: "source", status: "ok", message: "Key stored (no safe test endpoint)." };
  }

  let url = keyDef.test.url;
  const headers: Record<string, string> = {
    "user-agent": "BlackEclipse/1.0 (setup-check)",
  };
  if (keyDef.test.auth.kind === "query") {
    const u = new URL(url);
    u.searchParams.set(keyDef.test.auth.name, key);
    url = u.toString();
  } else {
    headers[keyDef.test.auth.name] = `${keyDef.test.auth.prefix ?? ""}${key}`;
  }

  const started = Date.now();
  try {
    const res = await fetch(url, { headers, signal: timeout(10_000) });
    const latencyMs = Date.now() - started;
    if (res.ok) {
      return { id, label, kind: "source", status: "ok", message: "Provider accepted the key.", latencyMs };
    }
    return {
      id, label, kind: "source",
      status: res.status === 429 ? "rate-limited" : "failed",
      message: `Provider rejected the request (HTTP ${res.status}).`,
      latencyMs, httpStatus: res.status,
    };
  } catch (err) {
    return {
      id, label, kind: "source", status: "failed",
      message: err instanceof Error ? `Could not reach provider: ${err.message}` : "Test failed",
      latencyMs: Date.now() - started,
    };
  }
}

export interface CheckOptions {
  ai?: boolean;
  aiConfig?: AiCheckOverride;
  sources?: string[];
}

export async function runSetupCheck(options: CheckOptions = {}): Promise<{
  ok: boolean;
  items: CheckItem[];
}> {
  const prefs = await effectiveSourcePreferences();
  const requested = Array.isArray(options.sources)
    ? options.sources.filter((id): id is SourceId => id in SOURCE_BY_ID)
    : Object.keys(SOURCE_BY_ID).filter((id): id is SourceId => prefs[id] === true);

  // Run every probe in parallel. A serial loop can exceed the route's
  // maxDuration when several included sources are slow (each has a 12s cap).
  const tasks: Array<Promise<CheckItem>> = [];
  if (options.ai !== false) tasks.push(testAi(options.aiConfig));

  for (const id of requested) {
    const def = SOURCE_BY_ID[id];
    if (!def) continue;
    if (prefs[id] !== true) {
      tasks.push(Promise.resolve({
        id, label: def.label, kind: "source", status: "skipped",
        message: "Disabled in setup.",
      }));
      continue;
    }
    if (def.tier === "included") {
      tasks.push(testIncludedSource(id));
      continue;
    }
    if (def.tier === "advanced") {
      tasks.push(Promise.resolve({
        id, label: def.label, kind: "source", status: "ok",
        message: "Community source enabled (personal use).",
      }));
      continue;
    }
    tasks.push(testKeyedSource(id));
  }

  const items = await Promise.all(tasks);
  const ok = items.every((i) => i.status === "ok" || i.status === "skipped");
  // Persist the last result so Settings/Review can show it after the modal is
  // closed. Best-effort: a failed write must not fail the check.
  try {
    await setConfig("setup_check_v1", JSON.stringify({ at: new Date().toISOString(), items }));
  } catch {
    /* non-fatal */
  }
  return { ok, items };
}
