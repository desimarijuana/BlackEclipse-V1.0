"use client";

// ── Problem-Solving & Recovery console ───────────────────────────────────────
// Failure incidents, their evidence-ranked diagnosis, the recovery decision and
// attempt history; plus unified capability discovery with an acquisition plan and
// operator-gated promotion of validated repairs into inert skill candidates.
// Talks to the Next proxy (`/api/recovery/*`), which forwards to the
// operator-gated Python routes. Renders with the frosted-glass system.

import { useCallback, useEffect, useState } from "react";
import { alertDialog } from "@/lib/ui/confirm-dialog";
import { PromoteChange } from "@/components/chat/promote-change";
import {
  countByStatus,
  diagnosisHeadline,
  formatIncidentLine,
  isRoutingRepairIncident,
  statusTone,
  type RecoveryAttemptView,
  type RecoveryDiagnosisView,
  type AcquisitionView,
  type RecoveryIncidentView,
  type RoutingRepairView,
} from "@/lib/harness/recovery-view";

type Tab = "incidents" | "discover" | "autonomy";

interface Health {
  status: string;
  enabled?: boolean;
  incidents?: number;
  byKind?: Record<string, number>;
}

interface DiscoverMatch {
  capability: { id: string; kind: string; description: string; available: boolean; provenance: string };
  score: number;
  reason: string;
}

interface AcquisitionPlan {
  resolvedBy: string | null;
  steps: { action: string; description: string; requiresApproval: boolean }[];
}

const inputClass =
  "rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-white/20";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/recovery${path}`, { cache: "no-store", ...init });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { error?: string; detail?: unknown }).error || `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body as T;
}

export function RecoveryConsole() {
  const [tab, setTab] = useState<Tab>("incidents");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Problem-Solving &amp; Recovery</h1>
          <p className="text-sm text-zinc-500">
            How Eclipse detects, diagnoses, decides about and learns from its own failures.
          </p>
        </div>
        <HealthBadge onError={setError} />
      </header>

      <nav className="glass-card-subtle flex flex-wrap gap-1 rounded-xl p-1 text-sm">
        {(["incidents", "discover", "autonomy"] as Tab[]).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`rounded-lg px-3 py-1.5 capitalize transition ${
              tab === key ? "bg-white/10 text-white" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {key === "discover" ? "Capability discovery" : key === "autonomy" ? "Autonomy & operations" : key}
          </button>
        ))}
      </nav>

      {error && <div className="glass-card-subtle rounded-xl border border-red-500/30 p-3 text-sm text-red-300">{error}</div>}

      {tab === "incidents" && <IncidentsTab onError={setError} />}
      {tab === "discover" && <DiscoverTab onError={setError} />}
      {tab === "autonomy" && <AutonomyTab onError={setError} />}
    </div>
  );
}

function HealthBadge({ onError }: { onError: (e: string | null) => void }) {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    api<Health>("/health").then(setHealth).catch((e) => onError(e instanceof Error ? e.message : "health failed"));
  }, [onError]);
  if (!health) return null;
  return (
    <div className="glass-card-subtle rounded-xl px-3 py-1.5 text-xs text-zinc-400">
      <span className={health.status === "ok" ? "text-emerald-300" : "text-amber-300"}>{health.status}</span>
      {typeof health.incidents === "number" && <span className="ml-2">{health.incidents} incident(s)</span>}
    </div>
  );
}

function IncidentsTab({ onError }: { onError: (e: string | null) => void }) {
  const [incidents, setIncidents] = useState<RecoveryIncidentView[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [current, setCurrent] = useState<RecoveryIncidentView | null>(null);
  const [attempts, setAttempts] = useState<RecoveryAttemptView[]>([]);
  const [diagnosis, setDiagnosis] = useState<RecoveryDiagnosisView | null>(null);
  const [repair, setRepair] = useState<RoutingRepairView | null>(null);
  const [repairError, setRepairError] = useState<string | null>(null);
  const [acquisition, setAcquisition] = useState<AcquisitionView | null>(null);
  const [acquisitionError, setAcquisitionError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const body = await api<{ incidents: RecoveryIncidentView[] }>(
        `/incidents${filter ? `?status=${encodeURIComponent(filter)}` : ""}`,
      );
      setIncidents(body.incidents ?? []);
    } catch (e) {
      onError(e instanceof Error ? e.message : "load failed");
    }
  }, [filter, onError]);

  useEffect(() => { void load(); }, [load]);

  const open = useCallback(async (id: string) => {
    setSelected(id);
    try {
      const body = await api<{ incident: RecoveryIncidentView; attempts: RecoveryAttemptView[] }>(`/incidents/${id}`);
      setCurrent(body.incident);
      setAttempts(body.attempts ?? []);
      setDiagnosis(body.incident.diagnosis);
      setRepair(null);
      setRepairError(null);
      setAcquisition(null);
      setAcquisitionError(null);
    } catch (e) {
      onError(e instanceof Error ? e.message : "detail failed");
    }
  }, [onError]);

  const approve = useCallback(async (id: string, strategy: string) => {
    try {
      await api(`/incidents/${id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy, approvedBy: "operator" }),
      });
      onError(null);
      await alertDialog({ title: `Approved '${strategy}' for ${id}.`, description: "The engine may now run it." });
    } catch (e) {
      onError(e instanceof Error ? e.message : "approve failed");
    }
  }, [onError]);

  const diagnose = useCallback(async (id: string) => {
    try {
      const body = await api<{ diagnosis: RecoveryDiagnosisView }>(`/incidents/${id}/diagnose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      setDiagnosis(body.diagnosis);
    } catch (e) {
      onError(e instanceof Error ? e.message : "diagnose failed");
    }
  }, [onError]);

  const prepareRepair = useCallback(async (id: string) => {
    setRepairError(null);
    try {
      const body = await api<RoutingRepairView & { success?: boolean }>(
        `/incidents/${id}/routing-repair`, { method: "POST" },
      );
      setRepair(body);
    } catch (e) {
      setRepairError(e instanceof Error ? e.message : "prepare failed");
    }
  }, []);

  const planAcquisition = useCallback(async (id: string) => {
    setAcquisitionError(null);
    try {
      const body = await api<{ acquisition: AcquisitionView }>(
        `/incidents/${id}/acquisition`, { method: "POST" },
      );
      setAcquisition(body.acquisition);
    } catch (e) {
      setAcquisitionError(e instanceof Error ? e.message : "acquisition plan failed");
    }
  }, []);

  const promote = useCallback(async () => {
    try {
      const body = await api<{ created: unknown[]; duplicates: string[] }>("/promote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minOccurrences: 2 }),
      });
      onError(null);
      setDiagnosis(null);
      await alertDialog({ title: `Promoted ${body.created.length} candidate(s); ${body.duplicates.length} duplicate(s) suppressed.` });
    } catch (e) {
      onError(e instanceof Error ? e.message : "promote failed");
    }
  }, [onError]);

  const counts = countByStatus(incidents);

  return (
    <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
      <section className="glass-card rounded-2xl p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <select className={inputClass} value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">all</option>
              <option value="open">open</option>
              <option value="resolved">resolved</option>
              <option value="failed">failed</option>
            </select>
            <span className="text-xs text-zinc-500">
              {incidents.length} shown{Object.keys(counts).length ? ` · ${Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(", ")}` : ""}
            </span>
          </div>
          <button onClick={() => void promote()} className="rounded-lg border border-white/10 px-2 py-1 text-xs text-zinc-300 hover:bg-white/5">
            Promote validated
          </button>
        </div>
        <ul className="flex flex-col divide-y divide-white/5">
          {incidents.map((incident) => (
            <li key={incident.id}>
              <button
                onClick={() => void open(incident.id)}
                className={`flex w-full flex-col items-start gap-1 rounded-lg px-2 py-2 text-left transition hover:bg-white/5 ${
                  selected === incident.id ? "bg-white/5" : ""
                }`}
              >
                <span className="text-xs text-zinc-200">{formatIncidentLine(incident)}</span>
                <span className="flex gap-2 text-[11px]">
                  <span className={statusTone(incident.status)}>{incident.status}</span>
                  <span className="text-zinc-600">{incident.lastSeenAt}</span>
                </span>
              </button>
            </li>
          ))}
          {incidents.length === 0 && <li className="py-6 text-center text-xs text-zinc-600">No incidents recorded.</li>}
        </ul>
      </section>

      <section className="glass-card rounded-2xl p-4">
        {!selected && <p className="text-xs text-zinc-600">Select an incident to inspect its diagnosis and attempts.</p>}
        {selected && (
          <div className="flex flex-col gap-3">
            <div>
              <h2 className="text-sm font-medium text-zinc-200">Diagnosis</h2>
              <p className="text-xs text-zinc-400">{diagnosisHeadline(diagnosis)}</p>
              <button onClick={() => void diagnose(selected)} className="mt-1 rounded-lg border border-white/10 px-2 py-1 text-[11px] text-zinc-300 hover:bg-white/5">
                Re-run diagnosis
              </button>
            </div>
            {current?.decision?.strategy && current.decision.action !== "stop" && (
              <div className="glass-card-subtle rounded-xl p-2">
                <p className="text-[11px] text-zinc-500">
                  decision: <span className="text-zinc-300">{current.decision.action}</span> · {current.decision.strategy}
                  {current.decision.requiresApproval ? " (needs approval)" : ""}
                </p>
                <button
                  onClick={() => void approve(selected, current.decision!.strategy!)}
                  className="mt-1 rounded-lg border border-amber-400/20 px-2 py-1 text-[11px] text-amber-200 hover:bg-white/5"
                >
                  Approve strategy
                </button>
              </div>
            )}
            {diagnosis?.hypotheses?.length ? (
              <ul className="flex flex-col gap-1">
                {diagnosis.hypotheses.slice(0, 5).map((h, i) => (
                  <li key={i} className="rounded-lg bg-white/5 px-2 py-1.5 text-[11px] text-zinc-300">
                    <span className="text-zinc-400">{Math.round(h.confidence * 100)}%</span> · {h.cause}
                    {h.test && <div className="text-zinc-600">test: {h.test}</div>}
                  </li>
                ))}
              </ul>
            ) : null}
            {isRoutingRepairIncident(current) && (
              <div className="glass-card-subtle rounded-xl p-2">
                <p className="text-[11px] text-zinc-500">
                  A verified routing repair can be prepared in a disposable copy; nothing lands without your confirmation.
                </p>
                {!repair && (
                  <button
                    onClick={() => void prepareRepair(selected)}
                    className="mt-1 rounded-lg border border-white/10 px-2 py-1 text-[11px] text-zinc-300 hover:bg-white/5"
                  >
                    Prepare self-repair
                  </button>
                )}
                {repairError && <p className="mt-1 text-[11px] text-red-300">{repairError}</p>}
                {repair && (
                  <div className="mt-1 flex flex-col gap-1 text-[11px] text-zinc-400">
                    <p>
                      <span className="text-zinc-300">{repair.proposal.cause}</span>
                      {" · "}{repair.proposal.summary}
                    </p>
                    <p className="text-zinc-500">
                      {repair.preview.filesChanged} file(s): {repair.preview.files.map((f) => f.path).join(", ")}
                    </p>
                    {repair.landing.restartRequired && (
                      <p className="text-amber-300">needs a runtime restart after landing</p>
                    )}
                    <PromoteChange runId={repair.runId} compact />
                  </div>
                )}
              </div>
            )}
            {current?.kind === "capability" && (
              <div className="glass-card-subtle rounded-xl p-2">
                <p className="text-[11px] text-zinc-500">
                  What can satisfy this need, and what would have to be approved?
                </p>
                {!acquisition && (
                  <button
                    onClick={() => void planAcquisition(selected)}
                    className="mt-1 rounded-lg border border-white/10 px-2 py-1 text-[11px] text-zinc-300 hover:bg-white/5"
                  >
                    Plan acquisition
                  </button>
                )}
                {acquisitionError && <p className="mt-1 text-[11px] text-red-300">{acquisitionError}</p>}
                {acquisition && (
                  <div className="mt-1 flex flex-col gap-1 text-[11px] text-zinc-400">
                    <p className="text-zinc-500">
                      {acquisition.resolvedBy
                        ? `resolved by ${acquisition.resolvedBy}`
                        : "no existing capability resolves this need"}
                    </p>
                    <ul className="flex flex-col gap-0.5">
                      {acquisition.steps.map((step, index) => (
                        <li key={`${step.action}:${index}`}>
                          <span className="text-zinc-300">{step.action}</span>
                          {" · "}{step.surface}
                          {step.ready ? " · ready" : ""}
                          {step.requiresApproval ? " · needs approval" : ""}
                          {step.missing.length ? ` · missing: ${step.missing.join("; ")}` : ""}
                        </li>
                      ))}
                    </ul>
                    <p className="text-zinc-600">
                      retry: {String(acquisition.retry.action ?? "resume_task")} from {String(acquisition.retry.from ?? "checkpoint")}
                    </p>
                  </div>
                )}
              </div>
            )}
            <div>
              <h2 className="text-sm font-medium text-zinc-200">Attempts</h2>
              <ul className="flex flex-col gap-1">
                {attempts.map((a) => (
                  <li key={a.id} className="text-[11px] text-zinc-400">
                    #{a.attemptNo} {a.action} {a.strategy ?? ""} → <span className="text-zinc-300">{a.outcome}</span>
                    {a.backoffMs ? <span className="text-zinc-600"> (+{a.backoffMs}ms)</span> : null}
                  </li>
                ))}
                {attempts.length === 0 && <li className="text-[11px] text-zinc-600">no attempts recorded</li>}
              </ul>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

interface EnvelopeView {
  enabled: boolean;
  actionClasses: string[];
  riskCeiling: string;
  requireReversible: boolean;
  maxCostUsd: number;
  maxFilesChanged: number;
  allowedNetwork: string[];
  expiresAt: string | null;
  source: string;
}

interface OperationView {
  id: string;
  kind: string;
  status: string;
  incidentId: string | null;
  compensatingAction: string | null;
  updatedAt: string;
}

function AutonomyTab({ onError }: { onError: (e: string | null) => void }) {
  const [envelope, setEnvelope] = useState<EnvelopeView | null>(null);
  const [operations, setOperations] = useState<OperationView[]>([]);

  useEffect(() => {
    api<{ envelope: EnvelopeView }>("/envelope")
      .then((b) => setEnvelope(b.envelope))
      .catch((e) => onError(e instanceof Error ? e.message : "envelope failed"));
    api<{ operations: OperationView[] }>("/operations")
      .then((b) => setOperations(b.operations ?? []))
      .catch((e) => onError(e instanceof Error ? e.message : "operations failed"));
  }, [onError]);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="glass-card rounded-2xl p-4">
        <h2 className="text-sm font-medium text-zinc-200">Autonomy envelope</h2>
        <p className="mb-2 text-[11px] text-zinc-500">
          The standing permission that lets the engine act unattended. It never overrides the security layer.
        </p>
        {envelope ? (
          <dl className="flex flex-col gap-1 text-[11px] text-zinc-400">
            <Row label="enabled" value={String(envelope.enabled)} tone={envelope.enabled ? "text-emerald-300" : "text-amber-300"} />
            <Row label="risk ceiling" value={envelope.riskCeiling} />
            <Row label="require reversible" value={String(envelope.requireReversible)} />
            <Row label="cost cap" value={`$${envelope.maxCostUsd}`} />
            <Row label="files cap" value={String(envelope.maxFilesChanged)} />
            <Row label="network" value={envelope.allowedNetwork.length ? envelope.allowedNetwork.join(", ") : "none"} />
            <Row label="expires" value={envelope.expiresAt ?? "never"} />
            <Row label="source" value={envelope.source} />
            <div className="mt-1 flex flex-wrap gap-1">
              {envelope.actionClasses.map((c) => (
                <span key={c} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-zinc-300">{c}</span>
              ))}
            </div>
          </dl>
        ) : (
          <p className="text-[11px] text-zinc-600">loading…</p>
        )}
      </section>
      <section className="glass-card rounded-2xl p-4">
        <h2 className="text-sm font-medium text-zinc-200">Operation ledger</h2>
        <p className="mb-2 text-[11px] text-zinc-500">
          Side-effecting repairs tracked with an idempotency key; uncompensated ones are reconcilable.
        </p>
        <ul className="flex flex-col divide-y divide-white/5">
          {operations.map((op) => (
            <li key={op.id} className="py-1.5 text-[11px] text-zinc-400">
              <span className="text-zinc-300">{op.kind}</span> → {op.status}
              {op.compensatingAction ? <span className="text-zinc-600"> · comp: {op.compensatingAction}</span> : null}
            </li>
          ))}
          {operations.length === 0 && <li className="py-2 text-[11px] text-zinc-600">no pending operations</li>}
        </ul>
      </section>
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-zinc-500">{label}</dt>
      <dd className={tone ?? "text-zinc-300"}>{value}</dd>
    </div>
  );
}

function DiscoverTab({ onError }: { onError: (e: string | null) => void }) {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<DiscoverMatch[]>([]);
  const [plan, setPlan] = useState<AcquisitionPlan | null>(null);

  const run = useCallback(async () => {
    if (!query.trim()) return;
    try {
      const body = await api<{ matches: DiscoverMatch[]; plan: AcquisitionPlan | null }>(
        `/discover?query=${encodeURIComponent(query)}`,
      );
      setMatches(body.matches ?? []);
      setPlan(body.plan);
    } catch (e) {
      onError(e instanceof Error ? e.message : "discover failed");
    }
  }, [query, onError]);

  return (
    <section className="glass-card rounded-2xl p-4">
      <div className="mb-3 flex gap-2">
        <input
          className={`${inputClass} flex-1`}
          placeholder="Describe the capability you need…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void run()}
        />
        <button onClick={() => void run()} className="rounded-lg border border-white/10 px-3 py-1 text-xs text-zinc-200 hover:bg-white/5">
          Find
        </button>
      </div>
      {matches.length > 0 && (
        <ul className="mb-3 flex flex-col divide-y divide-white/5">
          {matches.map((m) => (
            <li key={m.capability.id} className="flex flex-col gap-0.5 py-2 text-xs text-zinc-300">
              <span>
                {m.capability.id} <span className="text-zinc-500">({m.capability.kind}, {m.capability.provenance})</span>{" "}
                <span className={m.capability.available ? "text-emerald-300" : "text-amber-300"}>
                  {m.capability.available ? "available" : "unavailable"}
                </span>
              </span>
              <span className="text-[11px] text-zinc-600">{m.capability.description}</span>
            </li>
          ))}
        </ul>
      )}
      {plan && (
        <div className="glass-card-subtle rounded-xl p-3">
          <p className="text-xs text-zinc-400">
            {plan.resolvedBy ? (
              <>resolved by <span className="text-emerald-300">{plan.resolvedBy}</span></>
            ) : (
              "no existing capability fits — these routes require approval"
            )}
          </p>
          <ol className="mt-1 flex flex-col gap-0.5">
            {plan.steps.map((s, i) => (
              <li key={i} className="text-[11px] text-zinc-500">
                {s.action}: {s.description}
                {s.requiresApproval ? <span className="ml-1 text-amber-300">(approval)</span> : null}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}