"use client";

import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { usePageShortcuts } from "@/hooks/use-page-shortcuts";
import { useListNavigation } from "@/hooks/use-list-navigation";
import {
  Bell, Plus, Save, Trash2, Pencil, FlaskConical, X,
  CircleDot, History, Check, Zap, PencilLine, Inbox,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { TabBar } from "@/components/ui/tab-bar";
import { useSubroute } from "@/hooks/use-subroute";

// ─── Site design system (matches my-portfolio / market-overview) ──────────
// Frost glass — the default glass panel style used across every screen.
const PANEL = "glass-card border border-white/10 dark:border-white/5 rounded-2xl shadow-sm";
const TILE = "glass-card border border-white/10 dark:border-white/5 rounded-xl";

// ─── Types (mirror the server contract) ─────────────────────────────────

type Operator = ">" | "<" | ">=" | "<=" | "==" | "crosses_above" | "crosses_below" | "rising" | "falling" | "between";

interface Leaf {
  indicator: string;
  params?: Record<string, number>;
  operator: Operator;
  compareMode: "value" | "indicator";
  value?: number;
  value2?: number;
  compareIndicator?: string;
  compareParams?: Record<string, number>;
  offset?: number;
}

interface Group {
  children: Array<Leaf | Group>;
  logic: "AND" | "OR";
  negate?: boolean;
}

interface AlertRow {
  id: string;
  name: string;
  symbols: string[];
  market: string;
  logic: "AND" | "OR";
  conditions: unknown;
  timeframe: string;
  dataSource: string;
  intervalSec: number;
  cooldownMin: number;
  actions: { channels?: string[] };
  active: boolean;
  status: string;
  statusMsg?: string | null;
  lastFiredAt?: string | null;
}

interface EventRow {
  id: string;
  alertId: string;
  symbol: string;
  detail: string;
  firedAt: string;
}

interface NoticeRow {
  msg: string;
  firedAt: string;
  test?: boolean;
}

const SNAPSHOT_INDICATORS = ["CLOSE", "OPEN", "VOLUME", "CHANGE_PCT", "MARKET_CAP", "PE", "EPS", "SECTOR"];
const CANDLE_INDICATORS = ["SMA", "EMA", "RSI"];
const OPERATORS: Operator[] = [">", "<", ">=", "<=", "==", "crosses_above", "crosses_below", "rising", "falling", "between"];
const OP_LABELS: Record<Operator, string> = {
  ">": "above", "<": "below", ">=": "at or above", "<=": "at or below",
  "==": "touches", crosses_above: "crosses above", crosses_below: "crosses below",
  rising: "rising", falling: "falling", between: "between",
};
const CHANNELS = ["telegram", "discord", "ntfy", "email", "webhook"] as const;

const STATUS_STYLES: Record<string, string> = {
  idle: "text-muted-foreground bg-muted/20 border-border/30",
  warming: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  watching: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  triggered: "text-primary bg-primary/10 border-primary/25",
  error: "text-rose-400 bg-rose-500/10 border-rose-500/20",
};

type View = "watches" | "create" | "history";

// ─── Main client ─────────────────────────────────────────────────────────

export function AlertsClient() {
  const [view, setView] = useState<View>("watches");
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [notices, setNotices] = useState<NoticeRow[]>([]);
  const [editing, setEditing] = useState<AlertRow | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Global search: 'alerts.watches' | 'alerts.create' | 'alerts.history'.
  useSubroute('alerts', (req) => {
    const v = req.subroute as View;
    if (v === 'watches' || v === 'create' || v === 'history') {
      if (v !== 'create') setEditing(null);
      setView(v);
    }
  });

  const loadLive = useCallback(async () => {
    try {
      const res = await fetch("/api/alerts/live", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setEvents(data.events || []);
      setNotices(data.notices || []);
      // /api/alerts/live returns status-only rows (no symbols/market/etc.).
      // Patch existing rows in place; never let partial rows create entries,
      // otherwise WatchTable crashes on a.symbols before loadAll resolves.
      const live = new Map<string, Partial<AlertRow>>((data.watches || []).map((w: AlertRow) => [w.id, w]));
      setAlerts((prev) => prev.map((p) => {
        const patch = live.get(p.id);
        return patch ? { ...p, ...patch } : p;
      }));
    } catch {}
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const res = await fetch("/api/alerts", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch {}
  }, []);

  useEffect(() => {
    loadAll();
    loadLive();
    const t = setInterval(loadLive, 5000);
    return () => clearInterval(t);
  }, [loadAll, loadLive]);

  // Re-list whenever a watch is created elsewhere (e.g. the command palette's
  // `alert SYMBOL`). The Alerts tab is keep-alive (display:none), so switching
  // to it does not remount or fire focus — an explicit event is the reliable
  // signal. Also refresh on real browser-tab focus.
  useEffect(() => {
    const onChanged = () => loadAll();
    const onVisible = () => {
      if (document.visibilityState === 'visible') loadAll();
    };
    window.addEventListener('be:alerts-changed', onChanged);
    window.addEventListener('focus', onVisible);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('be:alerts-changed', onChanged);
      window.removeEventListener('focus', onVisible);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [loadAll]);

  const notify = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 5000);
  };

  const toggleActive = async (a: AlertRow) => {
    await fetch(`/api/alerts/${a.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: !a.active }),
    });
    loadAll();
  };

  const testFire = async (a: AlertRow) => {
    const res = await fetch(`/api/alerts/${a.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "test" }),
    });
    const data = await res.json();
    notify(
      data.failed?.length
        ? `Test sent, but delivery failed: ${data.failed.join("; ")}`
        : `Test alert fired — delivered via: ${data.delivered?.join(", ") || "in-app only (no channels configured)"}`
    );
    loadLive();
  };

  const remove = async (a: AlertRow) => {
    await fetch(`/api/alerts/${a.id}`, { method: "DELETE" });
    notify(`Deleted "${a.name}" — its history stays in Alert History.`);
    loadAll();
    loadLive();
  };

  const edit = (a: AlertRow) => {
    setEditing(a);
    setView("create");
  };

  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const startCreating = () => { setEditing(null); setView("create"); };
  const watchIds = useMemo(() => alerts.map((a) => a.id), [alerts]);
  const historyIds = useMemo(() => events.map((e) => e.id), [events]);
  const watchesNav = useListNavigation({
    ids: view === "watches" ? watchIds : [],
    rootRef: listRef,
    enabled: view === "watches",
    shortcutPrefix: "alerts.watches",
    onOpen: (id) => {
      const alert = alerts.find((a) => a.id === id);
      if (alert) edit(alert);
    },
  });
  const historyNav = useListNavigation({
    ids: view === "history" ? historyIds : [],
    rootRef: listRef,
    enabled: view === "history",
    shortcutPrefix: "alerts.history",
    onOpen: (id) => {
      const event = events.find((e) => e.id === id);
      if (event) notify(`${event.symbol} · ${event.detail}`);
    },
  });
  usePageShortcuts(rootRef, [
    { id: "alerts.new", label: "Create alert", keys: "Shift+N", run: startCreating, enabled: view !== "create" },
    { id: "alerts.refresh", label: "Refresh alerts", keys: "R", run: () => { void loadAll(); void loadLive(); }, enabled: view !== "create" },
  ]);

  const liveCount = alerts.filter((a) => a.active).length;
  const firedToday = events.filter((e) => Date.now() - new Date(e.firedAt).getTime() < 86400000).length;

  return (
    <div ref={rootRef} data-keyboard-scope="Alerts" className="space-y-8 p-6 md:p-10 font-sans bg-transparent min-h-full text-foreground animate-in fade-in duration-500 relative overflow-x-hidden w-full">

      {/* ─── HEADER ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b border-border/40 pb-6">
        <div>
          <h1 className="text-3xl md:text-4xl font-serif font-semibold tracking-tight flex items-center gap-3 flex-wrap">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
              <Bell className="text-primary" size={30} />
            </span>
            Price &amp; Condition Alerts
          </h1>
          <p className="text-muted-foreground text-sm mt-2">
            Watch prices, volumes and indicators — get notified on Telegram, Discord, ntfy or any webhook when conditions fire.
          </p>
        </div>
        <Button
          onClick={startCreating}
          className="cursor-pointer rounded-xl gap-1.5 shrink-0"
        >
          <Plus className="w-3.5 h-3.5" /> New Watch
        </Button>
      </div>

      {/* ─── STAT CARDS ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Live Watches", value: liveCount, sub: `${alerts.length} total`, icon: Zap },
          { label: "Fired (24h)", value: firedToday, sub: `${events.length} in history`, icon: History },
          { label: "In-App Notices", value: notices.length, sub: "latest 100", icon: Inbox },
          {
            label: "Watch Health",
            value: alerts.filter((a) => a.status === "error").length === 0 ? "OK" : "Issues",
            sub: alerts.filter((a) => a.status === "error").length === 0 ? "all monitors healthy" : `${alerts.filter((a) => a.status === "error").length} in error`,
            icon: CircleDot,
            warn: alerts.filter((a) => a.status === "error").length > 0,
          },
        ].map((s) => (
          <div key={s.label} className={cn(PANEL, "p-4 md:p-5 flex flex-col gap-1")}>
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5">
              <s.icon className="w-3 h-3" /> {s.label}
            </span>
            <span className={cn("text-2xl md:text-3xl font-serif font-semibold", s.warn ? "text-rose-400" : "text-foreground")}>{s.value}</span>
            <span className="text-[10px] text-muted-foreground">{s.sub}</span>
          </div>
        ))}
      </div>

      {/* ─── VIEW TABS (pill strip) ─────────────────────────────────────── */}
      <TabBar
        className="mb-5 flex-wrap"
        items={[
          { id: "watches", label: "Live Watches", icon: Zap },
          { id: "create", label: editing ? "Edit Watch" : "Create Watch", icon: PencilLine },
          {
            id: "history",
            label: "Alert History",
            icon: History,
            badge: events.length > 0 ? (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent/60 border border-border/30 text-muted-foreground uppercase tracking-wider">{events.length}</span>
            ) : undefined,
          },
        ]}
        activeId={view}
        onChange={(id) => { if (id !== "create") setEditing(null); setView(id as View); }}
      />

      {/* ─── TOAST ──────────────────────────────────────────────────────── */}
      {toast && (
        <div className="rounded-2xl border border-emerald-500/10 glass-card-subtle px-4 py-3 text-sm text-emerald-400 flex items-start gap-2 animate-fade-in">
          <Check className="w-4 h-4 mt-0.5 shrink-0" /> {toast}
          <button onClick={() => setToast(null)} className="ml-auto cursor-pointer opacity-60 hover:opacity-100"><X size={14} /></button>
        </div>
      )}

      {/* ─── CONTENT ────────────────────────────────────────────────────── */}
      {view === "watches" && (
        <WatchTable
          alerts={alerts}
          onEdit={edit}
          onToggle={toggleActive}
          onTest={testFire}
          onDelete={remove}
          tableRef={listRef}
          rowAttributes={watchesNav.rowAttributes}
          isSelected={watchesNav.isSelected}
        />
      )}
      {view === "create" && (
        <AlertBuilder
          editing={editing}
          onSaved={async (msg) => {
            notify(msg);
            setEditing(null);
            await loadAll();
            setView("watches");
          }}
          onCancel={() => { setEditing(null); setView("watches"); }}
        />
      )}
      {view === "history" && (
        <HistoryTable
          events={events}
          notices={notices}
          tableRef={listRef}
          rowAttributes={historyNav.rowAttributes}
          isSelected={historyNav.isSelected}
        />
      )}
    </div>
  );
}

// ─── Live watches table ─────────────────────────────────────────────────

function WatchTable({ alerts, onEdit, onTest, onToggle, onDelete, tableRef, rowAttributes, isSelected }: {
  alerts: AlertRow[];
  onEdit: (a: AlertRow) => void;
  onTest: (a: AlertRow) => void;
  onToggle: (a: AlertRow) => void;
  onDelete: (a: AlertRow) => void;
  tableRef: React.RefObject<HTMLDivElement | null>;
  rowAttributes: (id: string) => { 'data-list-id': string };
  isSelected: (id: string) => boolean;
}) {
  if (alerts.length === 0) {
    return (
      <div className={cn(PANEL, "p-10 text-center")}>
        <Bell className="mx-auto text-muted-foreground w-8 h-8 mb-3" />
        <p className="text-sm font-serif font-semibold text-foreground">No watches yet</p>
        <p className="text-xs text-muted-foreground mt-1">Create a watch and it starts polling immediately.</p>
      </div>
    );
  }
  return (
    <div ref={tableRef} className={cn(PANEL, "overflow-x-auto")}>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-widest text-muted-foreground border-b border-border/20">
            <th className="px-5 py-3.5 font-bold">Name</th>
            <th className="px-5 py-3.5 font-bold">Symbols</th>
            <th className="px-5 py-3.5 font-bold">Status</th>
            <th className="px-5 py-3.5 font-bold">Active</th>
            <th className="px-5 py-3.5 font-bold text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr
              key={a.id}
              {...rowAttributes(a.id)}
              className={cn("border-b border-border/10 last:border-0 hover:bg-accent/10 transition-colors", isSelected(a.id) && "bg-primary/10 ring-1 ring-inset ring-primary/40")}
            >
              <td className="px-5 py-3.5">
                <span className="font-serif font-semibold text-sm">{a.name}</span>
                <div className="text-[10px] text-muted-foreground mt-0.5">{a.market} · {a.timeframe} · every {a.intervalSec}s</div>
              </td>
              <td className="px-5 py-3.5">
                <div className="flex flex-wrap gap-1">
                  {(a.symbols || []).map((s) => (
                    <span key={s} className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent/60 border border-border/30 text-muted-foreground">{s}</span>
                  ))}
                </div>
              </td>
              <td className="px-5 py-3.5">
                <span className={cn("inline-flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full border", STATUS_STYLES[a.status] || STATUS_STYLES.idle)}>
                  <CircleDot size={10} /> {a.status}
                </span>
                {a.statusMsg && <div className="text-[10px] text-muted-foreground mt-1 max-w-[220px] truncate">{a.statusMsg}</div>}
              </td>
              <td className="px-5 py-3.5">
                <button
                  onClick={() => onToggle(a)}
                  className={cn(
                    "w-10 h-5.5 rounded-full relative transition-colors cursor-pointer shrink-0",
                    a.active ? "bg-emerald-500/70" : "bg-muted"
                  )}
                  title={a.active ? "Deactivate" : "Activate"}
                >
                  <span className={cn("absolute top-0.5 h-4.5 w-4.5 rounded-full bg-white shadow transition-all", a.active ? "left-5" : "left-0.5")} />
                </button>
              </td>
              <td className="px-5 py-3.5">
                <div className="flex items-center justify-end gap-1">
                  <Button size="sm" variant="ghost" onClick={() => onEdit(a)} title="Edit" className="cursor-pointer h-8 w-8 p-0"><Pencil size={13} /></Button>
                  <Button size="sm" variant="ghost" onClick={() => onTest(a)} title="Test delivery" className="cursor-pointer h-8 w-8 p-0"><FlaskConical size={13} /></Button>
                  <Button size="sm" variant="ghost" onClick={() => onDelete(a)} title="Delete (keeps history)" className="cursor-pointer h-8 w-8 p-0 hover:text-rose-400"><Trash2 size={13} /></Button>
                </div>
              </td>            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── History table ──────────────────────────────────────────────────────

function HistoryTable({ events, notices, tableRef, rowAttributes, isSelected }: {
  events: EventRow[];
  notices: NoticeRow[];
  tableRef: React.RefObject<HTMLDivElement | null>;
  rowAttributes: (id: string) => { 'data-list-id': string };
  isSelected: (id: string) => boolean;
}) {
  return (
    <div className="space-y-6">
      {notices.length > 0 && (
        <div className={cn(PANEL, "p-5")}>
          <h3 className="text-md font-serif font-semibold flex items-center gap-2 mb-3">
            <Inbox className="w-4 h-4 text-primary" /> Latest In-App Notices
          </h3>
          <div className="space-y-2">
            {notices.slice(0, 5).map((n, i) => (
              <div key={i} className={cn(TILE, "px-4 py-2.5 flex items-center justify-between gap-3 text-xs")}>
                <span className={cn(n.test && "text-primary")}>{n.msg}</span>
                <span className="text-[10px] text-muted-foreground whitespace-nowrap">{new Date(n.firedAt).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div ref={tableRef} className={cn(PANEL, "overflow-x-auto")}>
        <div className="px-5 py-3.5 border-b border-border/20">
          <h3 className="text-md font-serif font-semibold flex items-center gap-2">
            <History className="w-4 h-4 text-primary" /> Alert History
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent/60 border border-border/30 text-muted-foreground uppercase tracking-wider">recent 50</span>
          </h3>
        </div>
        {events.length === 0 ? (
          <p className="px-5 py-8 text-center text-xs text-muted-foreground">No fired alerts yet — they land here (and in your channels) the moment a watch triggers.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-widest text-muted-foreground border-b border-border/20">
                <th className="px-5 py-3 font-bold">Time</th>
                <th className="px-5 py-3 font-bold">Symbol</th>
                <th className="px-5 py-3 font-bold">Detail</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr
                  key={e.id}
                  {...rowAttributes(e.id)}
                  className={cn("border-b border-border/10 last:border-0 hover:bg-accent/10 transition-colors", isSelected(e.id) && "bg-primary/10 ring-1 ring-inset ring-primary/40")}
                >
                  <td className="px-5 py-2.5 text-xs text-muted-foreground whitespace-nowrap">{new Date(e.firedAt).toLocaleString()}</td>
                  <td className="px-5 py-2.5 font-mono text-xs">{e.symbol}</td>
                  <td className="px-5 py-2.5 text-xs">{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ─── Builder ────────────────────────────────────────────────────────────

function AlertBuilder({ editing, onSaved, onCancel }: {
  editing: AlertRow | null;
  onSaved: (msg: string) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbolInput, setSymbolInput] = useState("");
  const [market, setMarket] = useState("US");
  const [logic, setLogic] = useState<"AND" | "OR">("AND");
  const [timeframe, setTimeframe] = useState("1d");
  const [dataSource, setDataSource] = useState("Auto");
  const [intervalSec, setIntervalSec] = useState(60);
  const [cooldownMin, setCooldownMin] = useState(15);
  const [channels, setChannels] = useState<string[]>([]);
  const [root, setRoot] = useState<Group>({ children: [], logic: "AND" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (editing) {
      setName(editing.name);
      setSymbols(editing.symbols);
      setMarket(editing.market);
      setLogic(editing.logic);
      setTimeframe(editing.timeframe);
      setDataSource(editing.dataSource);
      setIntervalSec(editing.intervalSec);
      setCooldownMin(editing.cooldownMin);
      setChannels(editing.actions?.channels || []);
      const c = editing.conditions;
      setRoot(Array.isArray(c) ? { children: c as Array<Leaf | Group>, logic: editing.logic } : (c as Group) ?? { children: [], logic: "AND" });
    }
  }, [editing]);

  const addSymbol = async (rawSym?: string) => {
    const sym = (rawSym ?? symbolInput).trim().toUpperCase();
    if (!sym || symbols.includes(sym)) { setSymbolInput(""); setSuggestions([]); return; }
    setSymbols([...symbols, sym]);
    setSymbolInput("");
    setSuggestions([]);
    // Resolve current close and prefill an empty CLOSE value condition.
    try {
      const res = await fetch(`/api/quote?symbols=${encodeURIComponent(sym)}&market=${encodeURIComponent(market)}`);
      if (res.ok) {
        const data = await res.json();
        const quote = (data?.quotes || []).find((q: { symbol: string }) => q.symbol === sym);
        const price = typeof quote?.price === "number" ? quote.price : null;
        if (price && price > 0) {
          setRoot((r) => {
            const idx = r.children.findIndex((c) => !("children" in c) && c.indicator === "CLOSE" && (c.value === 0 || c.value === undefined));
            if (idx === -1) return r;
            const children = [...r.children];
            children[idx] = { ...(children[idx] as Leaf), value: price };
            return { ...r, children };
          });
        }
      }
    } catch {}
  };

  // ─── Symbol autocomplete (JDDS search via /api/quote?q=) ────────────────
  interface Suggestion {
    symbol: string;
    name: string;
    marketId: string;
    price: number;
    currency: string;
  }
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestOpen, setSuggestOpen] = useState(false);

  useEffect(() => {
    const q = symbolInput.trim();
    if (q.length < 1) { setSuggestions([]); setSuggestOpen(false); return; }
    const t = setTimeout(async () => {
      try {
        const res = await fetch(`/api/quote?q=${encodeURIComponent(q)}`);
        if (!res.ok) return;
        const data = await res.json();
        const list: Suggestion[] = (data.suggestions || []).slice(0, 8);
        setSuggestions(list);
        setSuggestOpen(list.length > 0);
      } catch {}
    }, 200); // debounce
    return () => clearTimeout(t);
  }, [symbolInput]);

  const save = async () => {
    if (!name || symbols.length === 0 || root.children.length === 0) return;
    setSaving(true);
    const body = {
      name, symbols, market, logic,
      conditions: root.children,
      timeframe, dataSource, intervalSec, cooldownMin,
      actions: { channels },
      active: true,
    };
    try {
      if (editing) {
        await fetch(`/api/alerts/${editing.id}`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, active: editing.active }),
        });
        onSaved(`Watch "${name}" updated — monitor restarted.`);
      } else {
        await fetch("/api/alerts", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        onSaved(`Watch "${name}" created — now live.`);
      }
    } finally {
      setSaving(false);
    }
  };

  const canSave = name && symbols.length > 0 && root.children.length > 0;

  return (
    <div className={cn(PANEL, "p-5 md:p-8 space-y-7 animate-fade-in-up")}>
      {/* Step 1 — basics */}
      <div className="space-y-4">
        <h3 className="text-md font-serif font-semibold flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-primary/15 text-primary text-[10px] font-bold flex items-center justify-center">1</span>
          Basics
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Watch name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. AAPL above 200" className="rounded-xl" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Market</Label>
            <Select value={market} onValueChange={(v) => setMarket(v ?? "US")}>
              <SelectTrigger className="w-full rounded-xl"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["US", "PK", "IN", "CRYPTO"].map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Symbols</Label>
          <div className="relative">
            <div className="flex gap-2">
              <Input
                value={symbolInput}
                onChange={(e) => setSymbolInput(e.target.value)}
                onFocus={() => { if (suggestions.length > 0) setSuggestOpen(true); }}
                onBlur={() => setTimeout(() => setSuggestOpen(false), 150)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") { e.preventDefault(); void addSymbol(); }
                  if (e.key === "Escape") setSuggestOpen(false);
                }}
                placeholder="Search by symbol or company name — e.g. AAPL or Apple"
                className="rounded-xl font-mono"
              />
              <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={() => void addSymbol()}><Plus size={13} /></Button>
            </div>
            {suggestOpen && suggestions.length > 0 && (
              <div className={cn(TILE, "absolute left-0 right-14 mt-1 z-50 overflow-hidden shadow-2xl divide-y divide-border/10")}>
                {suggestions.map((s) => (
                  <button
                    key={`${s.marketId}-${s.symbol}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => void addSymbol(s.symbol)}
                    className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-xs hover:bg-accent/40 transition-colors cursor-pointer"
                  >
                    <span className="flex items-center gap-2.5 min-w-0">
                      <span className="font-mono font-semibold text-foreground">{s.symbol}</span>
                      <span className="text-muted-foreground truncate max-w-[240px]">{s.name}</span>
                    </span>
                    <span className="flex items-center gap-2 shrink-0">
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent/60 border border-border/30 text-muted-foreground uppercase tracking-wider">{s.marketId}</span>
                      <span className="font-mono text-muted-foreground">{s.currency}{s.price?.toFixed?.(2) ?? s.price}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {symbols.map((s) => (
              <span key={s} className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 border border-primary/25 px-2.5 py-1 text-xs font-mono text-foreground">
                {s}
                <button onClick={() => setSymbols(symbols.filter((x) => x !== s))} className="cursor-pointer text-muted-foreground hover:text-rose-400"><X size={11} /></button>
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="border-t border-border/20" />

      {/* Step 2 — conditions */}
      <div className="space-y-4">
        <h3 className="text-md font-serif font-semibold flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-primary/15 text-primary text-[10px] font-bold flex items-center justify-center">2</span>
          Conditions
        </h3>
        <ConditionTree group={root} onChange={setRoot} logic={logic} onLogicChange={setLogic} />
      </div>

      <div className="border-t border-border/20" />

      {/* Step 3 — polling + delivery */}
      <div className="space-y-4">
        <h3 className="text-md font-serif font-semibold flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-primary/15 text-primary text-[10px] font-bold flex items-center justify-center">3</span>
          Polling &amp; Delivery
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Timeframe</Label>
            <Select value={timeframe} onValueChange={(v) => setTimeframe(v ?? "1d")}>
              <SelectTrigger className="w-full rounded-xl"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["1m", "5m", "15m", "1h", "1d"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Data source</Label>
            <Select value={dataSource} onValueChange={(v) => setDataSource(v ?? "Auto")}>
              <SelectTrigger className="w-full rounded-xl"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["Auto", "TradingView", "yfinance"].map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Poll interval</Label>
            <Select value={String(intervalSec)} onValueChange={(v) => setIntervalSec(Number(v))}>
              <SelectTrigger className="w-full rounded-xl"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[30, 60, 120, 300, 600].map((s) => <SelectItem key={s} value={String(s)}>{s < 60 ? `${s}s` : `${s / 60}m`}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Cooldown</Label>
            <Select value={String(cooldownMin)} onValueChange={(v) => setCooldownMin(Number(v))}>
              <SelectTrigger className="w-full rounded-xl"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[0, 5, 15, 30, 60].map((m) => <SelectItem key={m} value={String(m)}>{m === 0 ? "none" : `${m}m`}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Notify via</Label>
          <div className="flex flex-wrap gap-2">
            {CHANNELS.map((c) => (
              <button
                key={c}
                onClick={() => setChannels(channels.includes(c) ? channels.filter((x) => x !== c) : [...channels, c])}
                className={cn(
                  "rounded-full border px-3.5 py-1.5 text-xs font-semibold cursor-pointer transition-all capitalize",
                  channels.includes(c)
                    ? "bg-primary/15 border-primary/50 text-primary"
                    : "border-border/40 text-muted-foreground hover:text-foreground hover:border-primary/30 bg-card/40"
                )}
              >
                {channels.includes(c) ? <Check size={11} className="inline mr-1" /> : null}
                {c}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-muted-foreground">
            Configure channel credentials in <span className="text-primary font-semibold">Settings → Alerts</span>. A one-shot watch deactivates itself after firing; history is always kept.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2 border-t border-border/20">
        <Button onClick={save} disabled={saving || !canSave} className="cursor-pointer rounded-xl gap-1.5">
          <Save size={14} /> {editing ? "Save changes" : "Create watch"}
        </Button>
        <Button variant="ghost" onClick={onCancel} className="cursor-pointer rounded-xl">Cancel</Button>
        {!canSave && <span className="text-[10px] text-muted-foreground">Name, at least one symbol and one condition are required.</span>}
      </div>
    </div>
  );
}

// ─── Condition tree editor ──────────────────────────────────────────────

function ConditionTree({ group, onChange, logic, onLogicChange, depth = 0 }: {
  group: Group;
  onChange: (g: Group) => void;
  logic: "AND" | "OR";
  onLogicChange: (l: "AND" | "OR") => void;
  depth?: number;
}) {
  const addLeaf = () => onChange({ ...group, children: [...group.children, emptyLeafFor(group.children)] });
  const addGroup = () => onChange({ ...group, children: [...group.children, { children: [], logic: "AND" }] });

  return (
    <div className={cn(
      "rounded-2xl border p-4 space-y-3",
      depth === 0 ? "border-border/30 bg-accent/10" : "border-border/20 bg-muted/10"
    )}>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold">Match</span>
          <Select value={logic} onValueChange={(v) => onLogicChange((v ?? "AND") as "AND" | "OR")}>
            <SelectTrigger className="h-7 w-[86px] text-xs rounded-lg"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="AND">ALL (AND)</SelectItem>
              <SelectItem value="OR">ANY (OR)</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-[10px] text-muted-foreground">of the following</span>
        </div>
        <div className="flex gap-1.5">
          <Button size="sm" variant="outline" className="rounded-lg cursor-pointer h-7 text-[10px]" onClick={addLeaf}><Plus size={11} className="mr-1" />Condition</Button>
          {depth < 2 && <Button size="sm" variant="outline" className="rounded-lg cursor-pointer h-7 text-[10px]" onClick={addGroup}><Plus size={11} className="mr-1" />Group</Button>}
        </div>
      </div>

      {group.children.length === 0 && <p className="text-xs text-muted-foreground italic">No conditions yet — add one to start watching.</p>}

      <div className="space-y-2">
        {group.children.map((child, i) => {
          if ("children" in child) {
            return (
              <div key={i} className="flex items-start gap-2">
                <div className="flex-1 min-w-0">
                  <ConditionTree
                    group={child as Group}
                    logic={(child as Group).logic}
                    onLogicChange={(l) => {
                      const children = [...group.children];
                      children[i] = { ...(child as Group), logic: l };
                      onChange({ ...group, children });
                    }}
                    depth={depth + 1}
                    onChange={(g) => {
                      const children = [...group.children];
                      children[i] = g;
                      onChange({ ...group, children });
                    }}
                  />
                </div>
                <ChildRemove group={group} onChange={onChange} i={i} />
              </div>
            );
          }
          const leaf = child as Leaf;
          return (
            <div key={i} className="flex flex-wrap items-center gap-2 text-xs">
              <Select
                value={leaf.indicator}
                onValueChange={(v) => {
                  const ind = v ?? "CLOSE";
                  const children = [...group.children];
                  const next = { ...leaf, indicator: ind } as Leaf;
                  if (!SNAPSHOT_INDICATORS.includes(ind) && !CANDLE_INDICATORS.includes(ind)) next.params = { n: 14 };
                  children[i] = next;
                  onChange({ ...group, children });
                }}
              >
                <SelectTrigger className="h-9 w-40 rounded-xl"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SNAPSHOT_INDICATORS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  {CANDLE_INDICATORS.map((s) => <SelectItem key={s} value={s}>{s} (candles)</SelectItem>)}
                </SelectContent>
              </Select>
              {leaf.params && (
                <Input
                  type="number" min={2} className="h-9 w-20 rounded-xl font-mono"
                  value={leaf.params.n ?? 14}
                  title="period n"
                  onChange={(e) => {
                    const children = [...group.children];
                    children[i] = { ...leaf, params: { n: Number(e.target.value) } };
                    onChange({ ...group, children });
                  }}
                />
              )}
              <Select
                value={leaf.operator}
                onValueChange={(v) => {
                  const children = [...group.children];
                  children[i] = { ...leaf, operator: (v ?? ">") as Operator };
                  onChange({ ...group, children });
                }}
              >
                <SelectTrigger className="h-9 w-44 rounded-xl"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {OPERATORS.map((op) => <SelectItem key={op} value={op}>{OP_LABELS[op]}</SelectItem>)}
                </SelectContent>
              </Select>
              {leaf.operator !== "rising" && leaf.operator !== "falling" && (
                <Input
                  type="number" className="h-9 w-28 rounded-xl font-mono"
                  value={leaf.value ?? 0}
                  onChange={(e) => {
                    const children = [...group.children];
                    children[i] = { ...leaf, value: Number(e.target.value) };
                    onChange({ ...group, children });
                  }}
                />
              )}
              {leaf.operator === "between" && (
                <Input
                  type="number" className="h-9 w-28 rounded-xl font-mono" placeholder="to"
                  value={leaf.value2 ?? 0}
                  onChange={(e) => {
                    const children = [...group.children];
                    children[i] = { ...leaf, value2: Number(e.target.value) };
                    onChange({ ...group, children });
                  }}
                />
              )}
              {isCandleIndicator(leaf.indicator) && (
                <span className="text-[9px] font-bold uppercase tracking-widest text-amber-400">candles</span>
              )}
              <ChildRemove group={group} onChange={onChange} i={i} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function isCandleIndicator(ind: string) {
  return !SNAPSHOT_INDICATORS.includes(ind);
}

function ChildRemove({ group, onChange, i }: { group: Group; onChange: (g: Group) => void; i: number }) {
  return (
    <button
      onClick={() => onChange({ ...group, children: group.children.filter((_, j) => j !== i) })}
      className="text-muted-foreground hover:text-rose-400 cursor-pointer p-1.5 rounded-lg hover:bg-rose-500/10 transition-colors"
      title="Remove"
    >
      <Trash2 size={12} />
    </button>
  );
}

/** First added leaf defaults sensibly; second+ ones stay empty for prefill. */
function emptyLeafFor(existing: Array<Leaf | Group>): Leaf {
  const hasClose = existing.some((c) => !("children" in c) && (c as Leaf).indicator === "CLOSE");
  if (hasClose) return { indicator: "CHANGE_PCT", operator: ">", compareMode: "value" };
  return { indicator: "CLOSE", operator: ">", compareMode: "value", value: 0 };
}