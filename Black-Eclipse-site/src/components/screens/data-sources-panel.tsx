"use client";

// ── Data Sources settings panel ──────────────────────────────────────────────
// Operator-facing UI for the Universal Data Connector Layer. Reuses the
// existing glass-card / form / button primitives — no new design system.
//
// Flow: list connectors → add (wizard) → test connection → inspect response →
// define dataset → map fields → save. Credentials are sent to the server once
// and never returned: the UI only ever sees `hasSecret: boolean`.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Database, Plus, RefreshCcw, Trash2, Play, ChevronLeft, Check,
  AlertCircle, Loader2, Globe, KeyRound, ArrowRight,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { ProviderList } from "./provider-list";

// ─── Types ──────────────────────────────────────────────────────────────────

type Capability =
  | "PRICE" | "OHLCV" | "QUOTE" | "FUNDAMENTALS" | "NEWS" | "MACRO" | "CUSTOM_DATASET";

const CAPABILITIES: Capability[] = [
  "PRICE", "OHLCV", "QUOTE", "FUNDAMENTALS", "NEWS", "MACRO", "CUSTOM_DATASET",
];

type FieldType = "string" | "number" | "boolean" | "datetime" | "json";
const FIELD_TYPES: FieldType[] = ["string", "number", "boolean", "datetime", "json"];

interface PublicConnector {
  id: string;
  name: string;
  description: string | null;
  baseUrl: string;
  path: string;
  capabilities: Capability[];
  params: Array<{ name: string; value: string; required?: boolean }>;
  auth: { scheme: string; header: string | null; username: string | null };
  hasSecret: boolean;
  enabled: boolean;
  health: {
    state: string;
    lastTested: string | null;
    lastSuccess: string | null;
    lastError: string | null;
    httpStatus: number | null;
    latencyMs: number | null;
  };
}

interface FieldCandidate {
  path: string;
  type: string;
}

interface MappingField {
  name: string;
  type: FieldType;
  sourcePath: string;
  identity: boolean;
  required: boolean;
}

interface DatasetSummary {
  id: string;
  name: string;
  description: string | null;
  connectorId: string | null;
  recordPath: string;
  fieldCount: number;
  recordCount: number;
  pullParams: Record<string, string>;
  refreshEnabled: boolean;
  refreshIntervalMin: number;
  lastRefreshAt: string | null;
  nextRefreshAt: string | null;
  updatedAt: string;
}

interface DatasetRecord {
  id: string;
  recordKey: string;
  values: Record<string, unknown>;
  provenance: string;
  retrievedAt: string;
}

interface PullValueResult {
  value: string;
  ok: boolean;
  written: number;
  extracted: number;
  rejected: number;
  deduped: number;
  error?: string;
}

interface PullSummary {
  requested: number;
  attempted: number;
  succeeded: number;
  failed: number;
  written: number;
  extracted: number;
  rejected: number;
  overflow: number;
  truncated: boolean;
  provenance: string;
  results: PullValueResult[];
  error?: string;
}

interface Draft {
  name: string;
  description: string;
  baseUrl: string;
  path: string;
  capabilities: Capability[];
  method: "GET";
  paramName: string;
  paramTemplate: string;
  /** Sample value supplied to `{{paramName}}` when testing. */
  testValue: string;
  authScheme: "none" | "api_key" | "bearer" | "basic";
  authHeader: string;
  authUsername: string;
  secret: string;
}

const EMPTY_DRAFT: Draft = {
  name: "",
  description: "",
  baseUrl: "",
  path: "/",
  capabilities: ["PRICE"],
  method: "GET",
  paramName: "symbol",
  paramTemplate: "{{symbol}}",
  testValue: "AAPL",
  authScheme: "none",
  authHeader: "X-API-Key",
  authUsername: "",
  secret: "",
};

type WizardStep = 1 | 2 | 3 | 4;

// ─── Panel ──────────────────────────────────────────────────────────────────

export function DataSourcesPanel() {
  const [connectors, setConnectors] = useState<PublicConnector[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [step, setStep] = useState<WizardStep>(1);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    state: string;
    message: string;
    httpStatus?: number;
    latencyMs?: number;
    sample?: unknown;
  } | null>(null);
  const [mapping, setMapping] = useState<MappingField[]>([]);
  const [recordPath, setRecordPath] = useState("$");
  const [datasetName, setDatasetName] = useState("");

  // Datasets (the connector loop: pull → browse)
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [openDataset, setOpenDataset] = useState<string | null>(null);
  const [records, setRecords] = useState<DatasetRecord[]>([]);
  const [pulling, setPulling] = useState<string | null>(null);
  /**
   * Per-dataset values for the connector's declared parameters. A value may be
   * a comma-separated list — each entry becomes one request.
   */
  const [pullParams, setPullParams] = useState<Record<string, Record<string, string>>>({});

  const loadDatasets = useCallback(async () => {
    try {
      const res = await fetch("/api/datasets");
      const data = await res.json();
      if (Array.isArray(data.datasets)) setDatasets(data.datasets);
    } catch {
      /* dataset list is secondary — a failure must not blank the connector list */
    }
  }, []);

  const loadRecords = useCallback(async (datasetId: string) => {
    try {
      const res = await fetch(`/api/datasets?id=${encodeURIComponent(datasetId)}`);
      const data = await res.json();
      setRecords(Array.isArray(data.records) ? data.records : []);
    } catch {
      setRecords([]);
    }
  }, []);

  const openRecords = async (datasetId: string) => {
    if (openDataset === datasetId) {
      setOpenDataset(null);
      setRecords([]);
      return;
    }
    setOpenDataset(datasetId);
    setRecords([]);
    await loadRecords(datasetId);
  };

  /**
   * Parameters required to pull a dataset, taken from its connector. A dataset
   * with no connector, or whose connector declares nothing, needs no values.
   */
  const requiredParams = useCallback(
    (dataset: DatasetSummary): string[] => {
      const connector = connectors.find(
        (c) => c.id === dataset.connectorId || `custom:${c.id}` === dataset.connectorId
      );
      if (!connector) return [];
      return connector.params.map((p) => {
        const match = p.value.match(/^\{\{(\w+)\}\}$/);
        return match ? match[1] : p.name;
      });
    },
    [connectors]
  );

  const setPullParam = (datasetId: string, key: string, value: string) =>
    setPullParams((prev) => ({ ...prev, [datasetId]: { ...(prev[datasetId] ?? {}), [key]: value } }));

  const countValues = (raw: string | undefined) =>
    (raw ?? "")
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean).length;

  /**
   * Pull fresh data through the dataset's connector and ingest it. One request
   * per comma-separated value. Reports the honest outcome — succeeded/failed
   * requests and extracted vs. written vs. rejected rows.
   */
  const pullDataset = async (dataset: DatasetSummary) => {
    if (!dataset.connectorId) {
      setMessage(`"${dataset.name}" has no connector attached — it can only be filled via inline payloads.`);
      return;
    }
    const needed = requiredParams(dataset);
    const values = { ...dataset.pullParams, ...(pullParams[dataset.id] ?? {}) };
    const missing = needed.filter((k) => countValues(values[k]) === 0);
    if (missing.length > 0) {
      setMessage(`"${dataset.name}" needs a value for: ${missing.join(", ")}`);
      return;
    }
    setPulling(dataset.id);
    setMessage(null);
    try {
      const res = await fetch("/api/datasets", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ datasetId: dataset.id, params: values }),
      });
      const data = (await res.json()) as PullSummary;
      if (!res.ok && data.error) {
        setMessage(data.error);
        return;
      }
      const parts = [
        `${data.succeeded}/${data.attempted} request(s) ok`,
        `imported ${data.written} row(s)`,
      ];
      if (data.rejected > 0) parts.push(`${data.rejected} rejected`);
      if (data.truncated) parts.push(`capped at ${data.attempted}, ${data.overflow} value(s) skipped`);
      const failures = data.results.filter((r) => !r.ok);
      setMessage(
        `${dataset.name}: ${parts.join(" · ")}` +
          (failures.length > 0 ? ` — ${failures.length} failed (first: ${failures[0].error})` : "")
      );
      await Promise.all([loadDatasets(), openDataset === dataset.id ? loadRecords(dataset.id) : Promise.resolve()]);
    } catch {
      setMessage(`Pull failed for "${dataset.name}"`);
    } finally {
      setPulling(null);
    }
  };

  /** Toggle background refresh for a dataset. */
  const setRefresh = async (dataset: DatasetSummary, patch: { enabled?: boolean; minutes?: number }) => {
    await fetch("/api/datasets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: dataset.name,
        connectorId: dataset.connectorId,
        refreshEnabled: patch.enabled ?? dataset.refreshEnabled,
        refreshIntervalMin: patch.minutes ?? dataset.refreshIntervalMin,
      }),
    });
    await loadDatasets();
  };

  const removeDataset = async (datasetId: string) => {
    await fetch(`/api/datasets?id=${encodeURIComponent(datasetId)}`, { method: "DELETE" });
    if (openDataset === datasetId) {
      setOpenDataset(null);
      setRecords([]);
    }
    await loadDatasets();
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/data-sources");
      const data = await res.json();
      if (Array.isArray(data.connectors)) setConnectors(data.connectors);
      else setMessage(data.error || "Failed to load data sources");
    } catch {
      setMessage("Failed to load data sources");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    void loadDatasets();
  }, [load, loadDatasets]);

  const fields = useMemo<FieldCandidate[]>(() => {
    if (!testResult?.sample || typeof testResult.sample !== "object") return [];
    return flattenPaths(testResult.sample);
  }, [testResult]);

  const arrayPaths = useMemo(
    () => fields.filter((f) => f.type === "array").map((f) => `${f.path}[*]`),
    [fields]
  );

  const updateDraft = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));

  const testParams = useMemo(() => {
    const values: Record<string, string> = {};
    const match = draft.paramTemplate.match(/^\{\{(\w+)\}\}$/);
    if (match && draft.testValue) values[match[1]] = draft.testValue;
    if (draft.paramName && draft.testValue) values[draft.paramName] = draft.testValue;
    return values;
  }, [draft.paramTemplate, draft.paramName, draft.testValue]);

  const buildBody = () => ({
    name: draft.name,
    description: draft.description,
    baseUrl: draft.baseUrl,
    path: draft.path,
    capabilities: draft.capabilities,
    params: [{ name: draft.paramName, value: draft.paramTemplate, required: true }],
    auth: { scheme: draft.authScheme, header: draft.authHeader, username: draft.authUsername || undefined },
    secret: draft.secret || undefined,
  });

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/data-sources/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // `testParams` carries sample values for undeclared/declared placeholders.
        body: JSON.stringify({ ...buildBody(), testParams }),
      });
      const data = await res.json();
      setTestResult(data);
      if (data.ok && data.sample && typeof data.sample === "object") {
        // Auto-seed a single-object mapping; the operator refines it.
        const candidates = flattenPaths(data.sample);
        const seed: MappingField[] = candidates
          .filter((c) => c.type !== "object" && c.type !== "array")
          .slice(0, 5)
          .map((c) => ({
            name: c.path.split(".").pop()?.replace("[*]", "") ?? c.path,
            type: normalizeType(c.type),
            sourcePath: c.path,
            identity: c.path.includes("symbol") || c.path.includes("date"),
            required: false,
          }));
        setMapping(seed);
        setDatasetName(draft.name.toLowerCase().replace(/[^a-z0-9]+/g, "_"));
      }
    } catch {
      setTestResult({ ok: false, state: "ERROR", message: "Test request failed" });
    } finally {
      setTesting(false);
    }
  };

  const saveAll = async () => {
    setMessage(null);
    try {
      const createRes = await fetch("/api/data-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildBody()),
      });
      const created = await createRes.json();
      if (!createRes.ok) {
        setMessage(created.error || "Failed to save data source");
        return;
      }
      const connectorId = created.connector.id as string;
      let datasetSaveError: string | undefined;

      if (mapping.length > 0 && datasetName) {
        const dsRes = await fetch("/api/datasets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: datasetName,
            connectorId,
            // Persist the sample value as the default pull parameter so a
            // scheduled refresh has something to request with.
            pullParams: draft.testValue ? { [draft.paramName]: draft.testValue } : {},
            schema: {
              dataset: datasetName,
              recordPath,
              fields: mapping.map((m) => ({
                name: m.name,
                type: m.type,
                sourcePath: m.sourcePath,
                identity: m.identity,
                required: m.required,
              })),
            },
          }),
        });
        if (!dsRes.ok) {
          const dsErr = await dsRes.json().catch(() => ({}));
          datasetSaveError = dsErr.error || "dataset save failed";
        }
      }

      setMessage(
        datasetSaveError
          ? `Saved "${draft.name}" but the dataset was not created: ${datasetSaveError}`
          : `Saved "${draft.name}".`
      );
      setWizardOpen(false);
      setDraft(EMPTY_DRAFT);
      setTestResult(null);
      setMapping([]);
      setStep(1);
      await Promise.all([load(), loadDatasets()]);
    } catch {
      setMessage("Failed to save data source");
    }
  };

  const remove = async (id: string) => {
    await fetch(`/api/data-sources?id=${encodeURIComponent(id)}`, { method: "DELETE" });
    await Promise.all([load(), loadDatasets()]);
  };

  const toggleEnabled = async (connector: PublicConnector) => {
    await fetch("/api/data-sources", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: connector.id, enabled: !connector.enabled }),
    });
    await load();
  };

  return (
    <div className="animate-fade-in-up">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-primary font-bold mb-2">Connectors</p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 shadow-sm shadow-primary/10">
              <Database className="text-primary w-[18px] h-[18px]" />
            </div>
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Data Sources</h2>
          </div>
          <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-lg">
            Bring your own data API. Connected sources are stored in JDDS; custom data never overwrites
            scraper-sourced market rows.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={() => void load()}>
            <RefreshCcw className="w-4 h-4" />
          </Button>
          <Button
            size="sm"
            className="cursor-pointer rounded-xl"
            onClick={() => {
              setWizardOpen((v) => !v);
              setStep(1);
              setTestResult(null);
            }}
          >
            <Plus className="w-4 h-4 mr-1" /> Add Data Source
          </Button>
        </div>
      </div>

      {message && (
        <p className="text-xs text-muted-foreground mb-4 flex items-center gap-1.5">
          <AlertCircle className="w-3.5 h-3.5 text-primary" /> {message}
        </p>
      )}

      {/* Only "your own data" belongs here — the built-in providers live in the
          settings section for the page they serve (AI Agent, Market Data,
          Integrations). See `provider-list.tsx`. */}
      <ProviderList categories={["custom"]} onOpenWizard={() => setWizardOpen(true)} />

      <div className="h-6" />


      {wizardOpen && (
        <div className="rounded-2xl border border-primary/25 glass-card-strong overflow-hidden mb-6">
          <div className="px-5 py-4 border-b border-border/10 flex items-center gap-3">
            {step > 1 && (
              <button className="cursor-pointer text-muted-foreground hover:text-foreground" onClick={() => setStep((s) => (s - 1) as WizardStep)}>
                <ChevronLeft size={16} />
              </button>
            )}
            <div className="flex items-center gap-2">
              {[1, 2, 3, 4].map((n) => (
                <span
                  key={n}
                  className={cn(
                    "w-6 h-6 rounded-full text-[10px] font-bold flex items-center justify-center border",
                    step === n
                      ? "bg-primary/20 text-primary border-primary/40"
                      : step > n
                        ? "bg-primary/10 text-primary/70 border-primary/20"
                        : "text-muted-foreground border-border/40"
                  )}
                >
                  {step > n ? <Check size={11} /> : n}
                </span>
              ))}
            </div>
            <span className="text-xs text-muted-foreground">
              {step === 1 && "Configure"}
              {step === 2 && "Authenticate"}
              {step === 3 && "Test connection"}
              {step === 4 && "Map fields & define dataset"}
            </span>
          </div>

          <div className="p-5 space-y-4">
            {step === 1 && (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Name">
                    <Input value={draft.name} onChange={(e) => updateDraft({ name: e.target.value })} placeholder="My Market API" />
                  </Field>
                  <Field label="Base URL" hint="https only.">
                    <Input value={draft.baseUrl} onChange={(e) => updateDraft({ baseUrl: e.target.value })} placeholder="https://api.example.com" />
                  </Field>
                  <Field label="Endpoint / path">
                    <Input value={draft.path} onChange={(e) => updateDraft({ path: e.target.value })} placeholder="/quote" />
                  </Field>
                  <Field label="Method">
                    <Input value="GET" readOnly className="opacity-70" />
                  </Field>
                </div>
                <Field label="Capabilities">
                  <div className="flex flex-wrap gap-1.5">
                    {CAPABILITIES.map((c) => {
                      const active = draft.capabilities.includes(c);
                      return (
                        <button
                          key={c}
                          onClick={() =>
                            updateDraft({
                              capabilities: active
                                ? draft.capabilities.filter((x) => x !== c)
                                : [...draft.capabilities, c],
                            })
                          }
                          className={cn(
                            "px-2.5 py-1 rounded-full text-[10px] font-semibold border transition-all cursor-pointer",
                            active
                              ? "bg-primary/15 text-primary border-primary/40"
                              : "text-muted-foreground border-border/40 hover:text-foreground"
                          )}
                        >
                          {c}
                        </button>
                      );
                    })}
                  </div>
                </Field>
                <div className="grid gap-4 sm:grid-cols-3 border-t border-border/10 pt-4">
                  <Field label="Parameter name" hint="Sent as a query parameter.">
                    <Input value={draft.paramName} onChange={(e) => updateDraft({ paramName: e.target.value })} placeholder="symbol" />
                  </Field>
                  <Field label="Value template" hint="Only {{placeholders}} are substituted, and they are percent-encoded.">
                    <Input value={draft.paramTemplate} onChange={(e) => updateDraft({ paramTemplate: e.target.value })} placeholder="{{symbol}}" />
                  </Field>
                  <Field label="Sample test value" hint="Used only by Test Connection.">
                    <Input value={draft.testValue} onChange={(e) => updateDraft({ testValue: e.target.value })} placeholder="AAPL" />
                  </Field>
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <Field label="Authentication">
                  <Select
                    value={draft.authScheme}
                    onValueChange={(v) => updateDraft({ authScheme: (v ?? "none") as Draft["authScheme"] })}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None</SelectItem>
                      <SelectItem value="api_key">API Key</SelectItem>
                      <SelectItem value="bearer">Bearer Token</SelectItem>
                      <SelectItem value="basic">Basic Auth</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                {draft.authScheme === "api_key" && (
                  <Field label="Header name">
                    <Input value={draft.authHeader} onChange={(e) => updateDraft({ authHeader: e.target.value })} placeholder="X-API-Key" />
                  </Field>
                )}
                {draft.authScheme === "basic" && (
                  <Field label="Username">
                    <Input value={draft.authUsername} onChange={(e) => updateDraft({ authUsername: e.target.value })} placeholder="username" />
                  </Field>
                )}
                {draft.authScheme !== "none" && (
                  <Field label="Secret" hint="Encrypted at rest (AES-GCM) and never returned to the browser.">
                    <div className="relative">
                      <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                      <Input
                        type="password"
                        className="pl-9"
                        value={draft.secret}
                        onChange={(e) => updateDraft({ secret: e.target.value })}
                        placeholder="••••••••"
                      />
                    </div>
                  </Field>
                )}
              </>
            )}

            {step === 3 && (
              <>
                <div className="flex items-center gap-3">
                  <Button size="sm" className="cursor-pointer rounded-xl" onClick={() => void runTest()} disabled={testing}>
                    {testing ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Play className="w-4 h-4 mr-1" />}
                    {testing ? "Testing…" : "Test Connection"}
                  </Button>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    GET {draft.path} · timeout ≤10s · redirects blocked
                  </span>
                </div>
                {testResult && (
                  <div
                    className={cn(
                      "rounded-xl border p-4 text-xs space-y-1.5",
                      testResult.ok ? "border-primary/30 bg-primary/5" : "border-rose-500/30 bg-rose-500/5"
                    )}
                  >
                    <p className={cn("font-semibold flex items-center gap-1.5", testResult.ok ? "text-primary" : "text-rose-400")}>
                      {testResult.ok ? <Check size={13} /> : <AlertCircle size={13} />}
                      {testResult.message}
                    </p>
                    <p className="text-[10px] text-muted-foreground font-mono">
                      {testResult.httpStatus ? `HTTP ${testResult.httpStatus}` : "no response"}
                      {testResult.latencyMs !== undefined ? ` · ${testResult.latencyMs} ms` : ""}
                      {` · state: ${testResult.state}`}
                    </p>
                    {testResult.sample !== undefined && (
                      <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-black/40 p-3 text-[10px] leading-relaxed text-muted-foreground scrollbar-hide">
                        {JSON.stringify(testResult.sample, null, 2).slice(0, 4000)}
                      </pre>
                    )}
                  </div>
                )}
              </>
            )}

            {step === 4 && (
              <>
                {fields.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Run a successful test to inspect response fields.</p>
                ) : (
                  <>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="Dataset name">
                        <Input value={datasetName} onChange={(e) => setDatasetName(e.target.value)} placeholder="market_prices" />
                      </Field>
                      <Field label="Record path" hint="Which array becomes one record per element.">
                        <Select value={recordPath} onValueChange={(v) => setRecordPath(v ?? "$")}>
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="$">$ (single root object)</SelectItem>
                            {arrayPaths.map((p) => (
                              <SelectItem key={p} value={p}>{p}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </Field>
                    </div>
                    <div className="space-y-2">
                      {mapping.map((field, i) => (
                        <div key={i} className="flex flex-wrap items-center gap-2 rounded-xl border border-border/20 p-2.5">
                          <span className="text-[10px] text-muted-foreground font-mono min-w-[140px] truncate" title={field.sourcePath}>
                            {field.sourcePath}
                          </span>
                          <ArrowRight size={12} className="text-muted-foreground shrink-0" />
                          <Input
                            className="h-8 w-32 text-xs"
                            value={field.name}
                            onChange={(e) => setMapping(mapping.map((m, j) => (j === i ? { ...m, name: e.target.value } : m)))}
                          />
                          <Select
                            value={field.type}
                            onValueChange={(v) =>
                              setMapping(mapping.map((m, j) => (j === i ? { ...m, type: (v ?? "string") as FieldType } : m)))
                            }
                          >
                            <SelectTrigger className="h-8 w-28 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {FIELD_TYPES.map((t) => (
                                <SelectItem key={t} value={t}>{t}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <label className="flex items-center gap-1 text-[10px] text-muted-foreground cursor-pointer">
                            <input
                              type="checkbox"
                              checked={field.identity}
                              onChange={(e) =>
                                setMapping(mapping.map((m, j) => (j === i ? { ...m, identity: e.target.checked } : m)))
                              }
                            />
                            identity
                          </label>
                          <button
                            className="cursor-pointer text-muted-foreground hover:text-rose-400 ml-auto"
                            onClick={() => setMapping(mapping.filter((_, j) => j !== i))}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      ))}
                      <p className="text-[10px] text-muted-foreground flex items-center gap-1.5">
                        <Globe size={11} /> Identity fields form the dedup key — re-importing updates instead of duplicating.
                      </p>
                    </div>
                  </>
                )}
              </>
            )}
          </div>

          <div className="px-5 py-3.5 border-t border-border/10 flex items-center justify-between">
            <span className="text-[10px] text-muted-foreground">
              {step === 1 && "Configure the endpoint and parameters."}
              {step === 2 && "Credentials stay server-side after saving."}
              {step === 3 && "Guarded outbound request — SSRF, size and redirect protected."}
              {step === 4 && "Custom records are stored separately from canonical market data."}
            </span>
            <div className="flex items-center gap-2">
              {step < 4 ? (
                <Button
                  size="sm"
                  className="cursor-pointer rounded-xl"
                  onClick={() => {
                    if (step === 3) void runTest();
                    else setStep((s) => (s + 1) as WizardStep);
                  }}
                >
                  {step === 3 ? "Test" : "Next"} <ArrowRight className="w-3.5 h-3.5 ml-1" />
                </Button>
              ) : (
                <Button size="sm" className="cursor-pointer rounded-xl" onClick={() => void saveAll()}>
                  <Check className="w-4 h-4 mr-1" /> Save Data Source
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-xs text-muted-foreground flex items-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading data sources…
        </p>
      ) : connectors.length === 0 ? (
        <div className="rounded-2xl border border-border/20 glass-card p-8 text-center">
          <p className="text-xs text-muted-foreground">
            No operator data sources yet. Built-in sources (scraper, Binance crypto) are always available.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {connectors.map((c) => (
            <div key={c.id} className="rounded-2xl border border-border/20 glass-card p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground truncate">{c.name}</p>
                  <p className="text-[10px] text-muted-foreground font-mono truncate">{c.baseUrl}{c.path}</p>
                </div>
                <HealthDot state={c.health.state} enabled={c.enabled} />
              </div>
              <div className="flex flex-wrap gap-1">
                {c.capabilities.map((cap) => (
                  <span key={cap} className="px-2 py-0.5 rounded-full text-[9px] font-semibold border border-primary/25 bg-primary/10 text-primary">
                    {cap}
                  </span>
                ))}
              </div>
              <p className="text-[10px] text-muted-foreground">
                {c.health.lastTested ? `Last tested: ${new Date(c.health.lastTested).toLocaleString()}` : "Never tested"}
                {c.health.latencyMs !== null ? ` · ${c.health.latencyMs} ms` : ""}
                {c.hasSecret ? " · credential stored" : ""}
              </p>
              {c.health.lastError && <p className="text-[10px] text-rose-400 truncate">{c.health.lastError}</p>}
              <div className="flex items-center gap-2 pt-1">
                <Button variant="outline" size="sm" className="cursor-pointer rounded-xl text-[11px]" onClick={() => void toggleEnabled(c)}>
                  {c.enabled ? "Disable" : "Enable"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="cursor-pointer rounded-xl text-[11px] text-rose-400 hover:text-rose-300"
                  onClick={() => void remove(c.id)}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Datasets — the connector loop: pull fresh data, then browse records. */}
      <div className="mt-8">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] text-primary font-bold mb-1">Custom datasets</p>
            <p className="text-[11px] text-muted-foreground">
              Stored separately from canonical market data. Records are deduplicated by identity.
            </p>
          </div>
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={() => void loadDatasets()}>
            <RefreshCcw className="w-4 h-4" />
          </Button>
        </div>

        {datasets.length === 0 ? (
          <div className="rounded-2xl border border-border/20 glass-card p-6 text-center">
            <p className="text-xs text-muted-foreground">
              No datasets yet. Create one in the wizard above (step 4) to start pulling custom data.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {datasets.map((d) => (
              <div key={d.id} className="rounded-2xl border border-border/20 glass-card p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-foreground truncate">{d.name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {d.recordCount} record{d.recordCount === 1 ? "" : "s"} · {d.fieldCount} field{d.fieldCount === 1 ? "" : "s"} ·{" "}
                      <span className="font-mono">{d.recordPath}</span>
                      {d.connectorId ? "" : " · no connector"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="cursor-pointer rounded-xl text-[11px]"
                      disabled={pulling === d.id || !d.connectorId}
                      title={d.connectorId ? "Fetch through the connector and ingest" : "No connector attached"}
                      onClick={() => void pullDataset(d)}
                    >
                      {pulling === d.id ? (
                        <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                      ) : (
                        <Play className="w-3.5 h-3.5 mr-1" />
                      )}
                      Pull
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="cursor-pointer rounded-xl text-[11px]"
                      onClick={() => void openRecords(d.id)}
                    >
                      {openDataset === d.id ? "Hide" : "Records"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="cursor-pointer rounded-xl text-[11px] text-rose-400 hover:text-rose-300"
                      onClick={() => void removeDataset(d.id)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>

                {requiredParams(d).length > 0 && (
                  <div className="mt-3 flex flex-wrap items-end gap-2">
                    {requiredParams(d).map((key) => {
                      const raw = pullParams[d.id]?.[key] ?? d.pullParams?.[key] ?? "";
                      const n = countValues(raw);
                      return (
                        <div key={key} className="flex flex-col gap-1">
                          <Label className="text-[10px] text-muted-foreground font-medium">
                            {key}
                            {n > 1 && <span className="ml-1 text-primary">({n} values)</span>}
                          </Label>
                          <Input
                            className="h-8 w-44 text-xs"
                            value={raw}
                            onChange={(e) => setPullParam(d.id, key, e.target.value)}
                            placeholder="BTC, ETH, SOL"
                          />
                        </div>
                      );
                    })}
                    <span className="text-[10px] text-muted-foreground pb-2">comma-separate for multiple requests</span>
                  </div>
                )}

                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground cursor-pointer">
                    <input
                      type="checkbox"
                      checked={d.refreshEnabled}
                      onChange={(e) => void setRefresh(d, { enabled: e.target.checked })}
                    />
                    auto-refresh
                  </label>
                  {d.refreshEnabled && (
                    <div className="flex items-center gap-1.5">
                      <Input
                        type="number"
                        min={5}
                        max={1440}
                        className="h-7 w-20 text-xs"
                        value={d.refreshIntervalMin}
                        onChange={(e) => void setRefresh(d, { minutes: Number(e.target.value) })}
                      />
                      <span className="text-[10px] text-muted-foreground">min</span>
                    </div>
                  )}
                  <span className="text-[10px] text-muted-foreground">
                    {d.refreshEnabled
                      ? d.lastRefreshAt
                        ? `last ${new Date(d.lastRefreshAt).toLocaleString()}${d.nextRefreshAt ? ` · next ${new Date(d.nextRefreshAt).toLocaleTimeString()}` : ""}`
                        : "waiting for first run"
                      : ""}
                  </span>
                </div>

                {openDataset === d.id && (
                  <div className="mt-3 border-t border-border/10 pt-3">
                    {records.length === 0 ? (
                      <p className="text-[10px] text-muted-foreground">No records stored yet. Use Pull to fetch data.</p>
                    ) : (
                      <div className="overflow-x-auto scrollbar-hide">
                        <table className="w-full text-[10px]">
                          <thead>
                            <tr className="text-muted-foreground text-left">
                              <th className="pr-3 py-1 font-medium">key</th>
                              {Object.keys(records[0]?.values ?? {}).map((k) => (
                                <th key={k} className="pr-3 py-1 font-medium">{k}</th>
                              ))}
                              <th className="pr-3 py-1 font-medium">provenance</th>
                            </tr>
                          </thead>
                          <tbody>
                            {records.map((r) => (
                              <tr key={r.id} className="border-t border-border/10">
                                <td className="pr-3 py-1 font-mono text-foreground">{r.recordKey}</td>
                                {Object.keys(records[0]?.values ?? {}).map((k) => (
                                  <td key={k} className="pr-3 py-1 font-mono text-muted-foreground">
                                    {r.values[k] === undefined || r.values[k] === null ? "—" : String(r.values[k])}
                                  </td>
                                ))}
                                <td className="pr-3 py-1">
                                  <span className="px-1.5 py-0.5 rounded-full text-[9px] border border-primary/25 bg-primary/10 text-primary">
                                    {r.provenance}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
      {children}
      {hint && <p className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</p>}
    </div>
  );
}

function HealthDot({ state, enabled }: { state: string; enabled: boolean }) {
  const tone = !enabled
    ? "bg-muted-foreground/50"
    : state === "CONNECTED"
      ? "bg-emerald-400"
      : state === "AUTH_FAILED" || state === "RATE_LIMITED"
        ? "bg-amber-400"
        : state === "UNAVAILABLE"
          ? "bg-muted-foreground/50"
          : "bg-rose-400";
  return (
    <span className="flex items-center gap-1.5 shrink-0">
      <span className={cn("w-1.5 h-1.5 rounded-full", tone)} />
      <span className="text-[9px] uppercase tracking-wider text-muted-foreground">{enabled ? state : "DISABLED"}</span>
    </span>
  );
}

function normalizeType(type: string): FieldType {
  if (type === "number" || type === "boolean" || type === "datetime") return type;
  if (type === "object" || type === "array") return "json";
  return "string";
}

/** Flatten a JSON sample into selectable paths (mirrors `describeFields`). */
function flattenPaths(value: unknown, prefix = "", depth = 0, out: FieldCandidate[] = []): FieldCandidate[] {
  if (depth > 5 || out.length > 200) return out;
  if (Array.isArray(value)) {
    out.push({ path: prefix, type: "array" });
    if (value.length > 0) flattenPaths(value[0], `${prefix}[*]`, depth + 1, out);
    return out;
  }
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      const path = prefix ? `${prefix}.${key}` : key;
      if (child && typeof child === "object") {
        flattenPaths(child, path, depth + 1, out);
      } else {
        out.push({
          path,
          type:
            child === null
              ? "null"
              : typeof child === "number"
                ? "number"
                : typeof child === "boolean"
                  ? "boolean"
                  : "string",
        });
      }
    }
    return out;
  }
  return out;
}
