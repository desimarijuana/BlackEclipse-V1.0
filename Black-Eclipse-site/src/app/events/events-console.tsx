"use client";

// ── Event Console ────────────────────────────────────────────────────────────
// Live observability over the Event System: history, live tail, event detail,
// subscriptions, dead-letter queue, replay, correlation graph, metrics and the
// Event Registry. Talks to the Next proxy (`/api/events/*`), which forwards to
// the operator-gated Python console API. Renders with the frosted-glass system.

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import type {
  DeadLetterView,
  EclipseEventView,
  EventGraphView,
  RegistrySpecView,
  ReplayOutcomeView,
  SubscriptionView,
  DeclaredSubscriptionView,
} from "@/lib/harness/events-client";

type Tab = "history" | "live" | "dlq" | "subscriptions" | "registry" | "metrics" | "graph";

const inputClass =
  "rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-white/20";

const PRIORITY_TONE: Record<string, string> = {
  critical: "text-red-400",
  high: "text-amber-300",
  normal: "text-zinc-300",
  low: "text-zinc-500",
  bulk: "text-zinc-600",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/events${path}`, { cache: "no-store", ...init });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { error?: string; detail?: unknown }).error || `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body as T;
}

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "" && v !== null) search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export function EventsConsole() {
  const [tab, setTab] = useState<Tab>("history");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Event Console</h1>
          <p className="text-sm text-zinc-500">
            The reactive nervous system — durable events, consumers, retries, dead letters and replay.
          </p>
        </div>
      </header>

      <nav className="glass-card-subtle flex flex-wrap gap-1 rounded-xl p-1 text-sm">
        {(["history", "live", "dlq", "subscriptions", "registry", "metrics", "graph"] as Tab[]).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`rounded-lg px-3 py-1.5 capitalize transition ${
              tab === key ? "bg-white/10 text-white" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {key === "dlq" ? "Dead letter" : key}
          </button>
        ))}
      </nav>

      {error && <div className="glass-card-subtle rounded-xl border border-red-500/30 p-3 text-sm text-red-300">{error}</div>}

      {tab === "history" && <HistoryTab onError={setError} />}
      {tab === "live" && <LiveTab onError={setError} />}
      {tab === "dlq" && <DlqTab onError={setError} />}
      {tab === "subscriptions" && <SubscriptionsTab onError={setError} />}
      {tab === "registry" && <RegistryTab onError={setError} />}
      {tab === "metrics" && <MetricsTab onError={setError} />}
      {tab === "graph" && <GraphTab onError={setError} />}
    </div>
  );
}

function useFetch<T>(loader: () => Promise<T>, deps: unknown[], onError: (m: string) => void) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    loader()
      .then((value) => alive && setData(value))
      .catch((err) => alive && onError(err instanceof Error ? err.message : String(err)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, loading };
}

function HistoryTab({ onError }: { onError: (m: string) => void }) {
  const [type, setType] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [taskId, setTaskId] = useState("");
  const { data, loading } = useFetch(
    () => api<{ events: EclipseEventView[] }>(`${qs({ type, correlationId, taskId, limit: 100 })}`),
    [type, correlationId, taskId],
    onError,
  );
  const [selected, setSelected] = useState<EclipseEventView | null>(null);
  const events = data?.events ?? [];

  return (
    <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
      <div className="glass-card rounded-2xl p-3">
        <div className="mb-3 flex flex-wrap gap-2">
          <input className={inputClass} placeholder="type (task.completed)" value={type} onChange={(e) => setType(e.target.value)} />
          <input className={inputClass} placeholder="correlationId" value={correlationId} onChange={(e) => setCorrelationId(e.target.value)} />
          <input className={inputClass} placeholder="taskId" value={taskId} onChange={(e) => setTaskId(e.target.value)} />
        </div>
        {loading ? <p className="p-2 text-sm text-zinc-500">loading…</p> : (
          <ul className="max-h-[60vh] divide-y divide-white/5 overflow-y-auto text-sm">
            {events.map((event) => (
              <li key={event.id}>
                <button onClick={() => setSelected(event)} className="flex w-full items-center justify-between gap-3 px-2 py-2 text-left hover:bg-white/5">
                  <span className="truncate">
                    <span className="font-mono text-xs text-zinc-500">{event.timestamp.slice(11, 23)}</span>{" "}
                    <span className="font-medium">{event.type}</span>
                    <span className="ml-2 text-xs text-zinc-500">{event.source}</span>
                  </span>
                  <span className={`text-xs uppercase ${PRIORITY_TONE[event.priority] ?? "text-zinc-500"}`}>{event.priority}</span>
                </button>
              </li>
            ))}
            {!events.length && <li className="p-2 text-sm text-zinc-500">no events</li>}
          </ul>
        )}
      </div>
      <EventDetail event={selected} onError={onError} />
    </div>
  );
}

function EventDetail({ event, onError }: { event: EclipseEventView | null; onError: (m: string) => void }) {
  const [detail, setDetail] = useState<EclipseEventView | null>(null);
  useEffect(() => {
    if (!event) return setDetail(null);
    api<{ event: EclipseEventView }>(`/${encodeURIComponent(event.id)}`)
      .then((body) => setDetail(body.event))
      .catch((err) => onError(err instanceof Error ? err.message : String(err)));
  }, [event, onError]);
  if (!detail) return <div className="glass-card rounded-2xl p-4 text-sm text-zinc-500">Select an event to inspect it.</div>;
  const rows: Array<[string, string]> = [
    ["ID", detail.id], ["Type", detail.type], ["Version", String(detail.version)],
    ["Timestamp", detail.timestamp], ["Source", detail.source],
    ["Actor", detail.actor ? `${detail.actor.type}:${detail.actor.id}` : "—"],
    ["Correlation", detail.correlationId ?? "—"], ["Causation", detail.causationId ?? "—"],
    ["Trace", detail.traceId ?? "—"], ["Session", detail.sessionId ?? "—"],
    ["Task", detail.taskId ?? "—"], ["Workflow", detail.workflowId ?? "—"], ["Agent", detail.agentId ?? "—"],
    ["Depth", String(detail.depth)], ["Replay", detail.replay ? "yes" : "no"],
  ];
  return (
    <div className="glass-card rounded-2xl p-4">
      <h2 className="mb-2 text-sm font-semibold">Event detail</h2>
      <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1 text-xs">
        {rows.map(([k, v]) => (
          <FragmentRow key={k} label={k} value={v} />
        ))}
      </dl>
      <pre className="mt-3 max-h-48 overflow-auto rounded-lg bg-black/30 p-2 text-[11px] text-zinc-300">{JSON.stringify(detail.payload, null, 2)}</pre>
      {detail.consumers && detail.consumers.length > 0 && (
        <div className="mt-3">
          <h3 className="mb-1 text-xs font-semibold text-zinc-400">Consumers</h3>
          <ul className="space-y-1 text-[11px] text-zinc-400">
            {detail.consumers.map((c, i) => (
              <li key={i}>{c.consumerId} · {c.status} · attempts {c.attempts ?? 0}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function FragmentRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-zinc-500">{label}</dt>
      <dd className="truncate font-mono text-zinc-300">{value}</dd>
    </>
  );
}

function LiveTab({ onError }: { onError: (m: string) => void }) {
  const [events, setEvents] = useState<EclipseEventView[]>([]);
  const [paused, setPaused] = useState(false);
  const load = useCallback(() => {
    api<{ events: EclipseEventView[] }>(`${qs({ limit: 50 })}`)
      .then((body) => setEvents(body.events ?? []))
      .catch((err) => onError(err instanceof Error ? err.message : String(err)));
  }, [onError]);
  useEffect(() => {
    load();
    if (paused) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [load, paused]);
  return (
    <div className="glass-card rounded-2xl p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm text-zinc-400">Live tail (2s poll)</span>
        <button className="glass-button rounded-lg px-3 py-1 text-xs" onClick={() => setPaused((p) => !p)}>
          {paused ? "Resume" : "Pause"}
        </button>
      </div>
      <ul className="max-h-[70vh] divide-y divide-white/5 overflow-y-auto font-mono text-xs">
        {events.map((event) => (
          <li key={event.id} className="flex items-center gap-2 px-2 py-1.5">
            <span className="text-zinc-600">{event.timestamp.slice(11, 23)}</span>
            <span className={PRIORITY_TONE[event.priority] ?? "text-zinc-300"}>{event.type}</span>
            <span className="truncate text-zinc-600">{event.source}</span>
          </li>
        ))}
        {!events.length && <li className="p-2 text-zinc-500">no events yet</li>}
      </ul>
    </div>
  );
}

function DlqTab({ onError }: { onError: (m: string) => void }) {
  const [entries, setEntries] = useState<DeadLetterView[]>([]);
  const [outcome, setOutcome] = useState<ReplayOutcomeView | null>(null);
  const reload = useCallback(() => {
    api<{ deadLetters: DeadLetterView[] }>("/dlq")
      .then((body) => setEntries(body.deadLetters ?? []))
      .catch((err) => onError(err instanceof Error ? err.message : String(err)));
  }, [onError]);
  useEffect(reload, [reload]);
  const retry = async (id: string) => {
    try {
      const body = await api<{ replay: ReplayOutcomeView }>(`/dlq/${encodeURIComponent(id)}/retry`, { method: "POST" });
      setOutcome(body.replay);
      reload();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  };
  const discard = async (id: string) => {
    await api(`/dlq/${encodeURIComponent(id)}/discard`, { method: "POST" }).catch((e) => onError(String(e)));
    reload();
  };
  return (
    <div className="glass-card rounded-2xl p-3">
      {outcome && <p className="mb-2 text-xs text-emerald-300">replay: {outcome.delivered} delivered of {outcome.count}</p>}
      <table className="w-full text-left text-xs">
        <thead className="text-zinc-500">
          <tr><th className="p-2">Type</th><th className="p-2">Consumer</th><th className="p-2">Error</th><th className="p-2">Attempts</th><th className="p-2"></th></tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id} className="border-t border-white/5">
              <td className="p-2 font-mono">{entry.eventType}</td>
              <td className="p-2">{entry.consumerId}</td>
              <td className="max-w-xs truncate p-2 text-zinc-400" title={entry.error ?? ""}>{entry.errorClass}: {entry.error}</td>
              <td className="p-2">{entry.attempts}</td>
              <td className="p-2">
                <button className="glass-button mr-2 rounded px-2 py-0.5" onClick={() => retry(entry.id)}>Retry</button>
                <button className="glass-button rounded px-2 py-0.5" onClick={() => discard(entry.id)}>Discard</button>
              </td>
            </tr>
          ))}
          {!entries.length && <tr><td colSpan={5} className="p-2 text-zinc-500">dead letter queue is empty</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function SubscriptionsTab({ onError }: { onError: (m: string) => void }) {
  const [live, setLive] = useState<SubscriptionView[]>([]);
  const [declared, setDeclared] = useState<DeclaredSubscriptionView[]>([]);
  const [subscriberId, setSubscriberId] = useState("");
  const [patterns, setPatterns] = useState("");
  const reload = useCallback(() => {
    api<{ live: SubscriptionView[]; declared: DeclaredSubscriptionView[] }>("/subscriptions")
      .then((body) => { setLive(body.live ?? []); setDeclared(body.declared ?? []); })
      .catch((err) => onError(err instanceof Error ? err.message : String(err)));
  }, [onError]);
  useEffect(reload, [reload]);
  const declare = async () => {
    try {
      await api("/subscriptions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscriberId, patterns: patterns.split(",").map((p) => p.trim()).filter(Boolean) }),
      });
      setSubscriberId("");
      setPatterns("");
      reload();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="glass-card rounded-2xl p-4">
        <h2 className="mb-2 text-sm font-semibold">Live consumers</h2>
        <ul className="space-y-1 text-xs">
          {live.map((sub) => (
            <li key={sub.consumerId} className="flex justify-between border-b border-white/5 py-1">
              <span className="font-mono">{sub.consumerId}</span>
              <span className="text-zinc-500">{sub.patterns.join(", ")} · {sub.delivered} delivered · {sub.errors} errors · q{sub.queueDepth}</span>
            </li>
          ))}
          {!live.length && <li className="text-zinc-500">no live consumers (runtime may be stopped)</li>}
        </ul>
      </div>
      <div className="glass-card rounded-2xl p-4">
        <h2 className="mb-2 text-sm font-semibold">Declared subscriptions</h2>
        <div className="mb-3 flex flex-wrap gap-2">
          <input className={inputClass} placeholder="subscriberId" value={subscriberId} onChange={(e) => setSubscriberId(e.target.value)} />
          <input className={inputClass} placeholder="task.completed, market.**" value={patterns} onChange={(e) => setPatterns(e.target.value)} />
          <button className="glass-button rounded-lg px-3 py-1 text-xs" onClick={declare} disabled={!subscriberId || !patterns}>Declare</button>
        </div>
        <ul className="space-y-1 text-xs">
          {declared.map((sub) => (
            <li key={sub.subscriberId + sub.patterns.join()} className="flex justify-between border-b border-white/5 py-1">
              <span className="font-mono">{sub.subscriberId}</span>
              <span className="text-zinc-500">{sub.patterns.join(", ")}</span>
            </li>
          ))}
          {!declared.length && <li className="text-zinc-500">none declared</li>}
        </ul>
      </div>
    </div>
  );
}

function RegistryTab({ onError }: { onError: (m: string) => void }) {
  const { data, loading } = useFetch(() => api<{ events: RegistrySpecView[] }>("/registry"), [], onError);
  const specs = data?.events ?? [];
  return (
    <div className="glass-card rounded-2xl p-3">
      {loading ? <p className="text-sm text-zinc-500">loading…</p> : (
        <table className="w-full text-left text-xs">
          <thead className="text-zinc-500">
            <tr><th className="p-2">Type</th><th className="p-2">Priority</th><th className="p-2">Retention</th><th className="p-2">Producer</th><th className="p-2">Sensitive</th></tr>
          </thead>
          <tbody>
            {specs.map((spec) => (
              <tr key={spec.type} className="border-t border-white/5">
                <td className="p-2 font-mono">{spec.type}{spec.namespace ? ".**" : ""}</td>
                <td className={`p-2 ${PRIORITY_TONE[spec.priority] ?? ""}`}>{spec.priority}</td>
                <td className="p-2 text-zinc-400">{spec.retentionDays}d</td>
                <td className="p-2 text-zinc-400">{spec.producer.join(", ")}</td>
                <td className="p-2 text-zinc-400">{spec.sensitive ? "yes" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function MetricsTab({ onError }: { onError: (m: string) => void }) {
  const { data } = useFetch(() => api<Record<string, unknown>>("/metrics"), [], onError);
  const byType = (data?.byType ?? {}) as Record<string, number>;
  const cards: Array<[string, unknown]> = data
    ? Object.entries(data).filter(([k]) => !["byType", "processingLatencyMs", "queueLatencyMs"].includes(k))
    : [];
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {cards.map(([key, value]) => (
          <div key={key} className="glass-card rounded-2xl p-3">
            <p className="text-xs text-zinc-500">{key}</p>
            <p className="text-lg font-semibold">{typeof value === "object" ? JSON.stringify(value) : String(value)}</p>
          </div>
        ))}
      </div>
      <div className="glass-card rounded-2xl p-4">
        <h2 className="mb-2 text-sm font-semibold">By event type</h2>
        <ul className="grid gap-1 text-xs sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(byType).map(([type, count]) => (
            <li key={type} className="flex justify-between border-b border-white/5 py-0.5">
              <span className="font-mono">{type}</span><span className="text-zinc-500">{count}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function GraphTab({ onError }: { onError: (m: string) => void }) {
  const [correlationId, setCorrelationId] = useState("");
  const { data } = useFetch(
    () => (correlationId ? api<EventGraphView>(`/graph${qs({ correlationId })}`) : Promise.resolve({ nodes: [], edges: [], root: null })),
    [correlationId],
    onError,
  );
  const childrenOf = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const edge of data?.edges ?? []) {
      map.set(edge.from, [...(map.get(edge.from) ?? []), edge.to]);
    }
    return map;
  }, [data]);
  const nodeById = useMemo(() => {
    const map = new Map<string, Record<string, unknown>>();
    for (const node of data?.nodes ?? []) map.set(String(node.id), node);
    return map;
  }, [data]);

  const renderNode = (id: string, depth: number): ReactNode => {
    const node = nodeById.get(id);
    return (
      <li key={id} style={{ marginLeft: depth * 16 }}>
        <span className="font-mono text-xs">{String(node?.type ?? id)}</span>
        <span className="ml-2 text-[10px] text-zinc-600">{String(node?.timestamp ?? "").slice(11, 23)}</span>
        {(childrenOf.get(id) ?? []).map((child) => renderNode(child, depth + 1))}
      </li>
    );
  };

  const roots = (data?.nodes ?? []).map((n) => String(n.id)).filter((id) => !(data?.edges ?? []).some((e) => e.to === id));
  return (
    <div className="flex flex-col gap-3">
      <input className={inputClass} placeholder="correlationId" value={correlationId} onChange={(e) => setCorrelationId(e.target.value)} />
      <div className="glass-card rounded-2xl p-4">
        <ul className="space-y-1 text-sm">{roots.map((id) => renderNode(id, 0))}</ul>
        {!roots.length && <p className="text-sm text-zinc-500">Enter a correlation id to see its execution graph (built from causation links).</p>}
      </div>
    </div>
  );
}
