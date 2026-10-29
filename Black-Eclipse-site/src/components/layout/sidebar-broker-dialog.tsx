"use client";

// ── Sidebar broker button + connect dialog ───────────────────────────────────
// A first-class “connect MT5” entry point in the shell footer. It creates,
// probes and reads a broker connection; it never places an order. Live arming
// and mandates stay in Settings → Broker connection.

import { useCallback, useEffect, useState } from "react";
import { Handshake, Loader2, RefreshCw } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  createBrokerConnection,
  listBrokerConnections,
  listBrokerKinds,
  syncBrokerConnection,
  testBrokerConnection,
  type BrokerAccount,
  type BrokerConnection,
  type BrokerKind,
} from "@/lib/harness/trading-client";

const DEFAULT_TERMINAL = "C:\\Program Files\\MetaTrader 5\\terminal64.exe";
const inputClass =
  "w-full rounded-xl border border-border/40 bg-transparent px-2.5 py-1.5 text-xs text-foreground focus:border-primary/40 focus:outline-none";

export function SidebarBrokerButton({
  collapsed = false,
  variant = "footer",
}: {
  collapsed?: boolean;
  variant?: "footer" | "launcher";
}) {
  const [open, setOpen] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    listBrokerConnections()
      .then((connections) => {
        if (alive) setConnected(connections.some((c) => c.status === "connected"));
      })
      .catch(() => {
        if (alive) setConnected(false);
      });
    return () => {
      alive = false;
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "relative shrink-0 text-muted-foreground transition-colors hover:bg-white/[0.04] hover:text-foreground outline-none focus-visible:ring-1 focus-visible:ring-primary/50 cursor-pointer",
          variant === "launcher"
            ? "flex h-7 w-7 items-center justify-center rounded-md"
            : "rounded-lg p-1.5 hover:bg-accent",
          collapsed && "flex h-9 w-9 items-center justify-center rounded-lg",
        )}
        title="Broker connection (MetaTrader)"
        aria-label="Broker connection (MetaTrader)"
      >
        <Handshake size={variant === "launcher" ? 15 : 16} className="shrink-0" />
        {connected != null && (
          <span
            className={cn(
              "absolute right-1 top-1 h-1.5 w-1.5 rounded-full",
              connected ? "bg-emerald-400" : "bg-amber-400",
            )}
          />
        )}
      </button>
      <SidebarBrokerDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

function SidebarBrokerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [kinds, setKinds] = useState<BrokerKind[]>([]);
  const [connections, setConnections] = useState<BrokerConnection[]>([]);
  const [account, setAccount] = useState<BrokerAccount | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [label, setLabel] = useState("MT5 demo");
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [terminalPath, setTerminalPath] = useState(DEFAULT_TERMINAL);
  const [magic, setMagic] = useState("0");
  const [maxMargin, setMaxMargin] = useState("0");

  const connection = connections[0] ?? null;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextKinds, nextConnections] = await Promise.all([
        listBrokerKinds(),
        listBrokerConnections(),
      ]);
      setKinds(nextKinds);
      setConnections(nextConnections);
      setShowForm(nextConnections.length === 0);
      // Use the account snapshot the connection row already holds. A live
      // account read is what Test is for; it must not block opening the dialog.
      setAccount(nextConnections[0]?.account ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "broker settings unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const run = async (key: string, action: () => Promise<unknown>, done: string) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(done);
    } catch (err) {
      setError(err instanceof Error ? err.message : "the action failed");
    } finally {
      setBusy(null);
    }
  };

  const add = () => {
    void run("create", async () => {
      const config: Record<string, unknown> = { terminalPath: terminalPath.trim() };
      const magicNumber = Number(magic);
      const marginNumber = Number(maxMargin);
      if (Number.isFinite(magicNumber) && magicNumber > 0) config.magic = magicNumber;
      if (Number.isFinite(marginNumber) && marginNumber > 0) config.maxMargin = marginNumber;
      const created = await createBrokerConnection({
        kind: "mt5",
        label: label.trim() || "MT5",
        mode,
        config,
      });
      await testBrokerConnection(created.id);
    }, "Connection added and tested.");
  };

  const test = () => {
    if (!connection) return;
    void run("test", () => testBrokerConnection(connection.id), "Connection tested.");
  };

  const sync = () => {
    if (!connection) return;
    void run("sync", () => syncBrokerConnection(connection.id), "Fills and positions synced.");
  };

  const mt5 = kinds.find((kind) => kind.id === "mt5");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[min(85dvh,800px)] w-[calc(100vw-2rem)] max-w-none flex-col gap-0 overflow-hidden rounded-2xl border border-white/10 glass-card-strong p-0 text-foreground sm:max-w-lg">
        <DialogHeader className="shrink-0 border-b border-border/10 px-5 py-3.5">
          <DialogTitle className="flex items-center gap-2 text-sm font-semibold">
            <Handshake size={15} className="text-muted-foreground" /> Broker connection
            <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-sky-300">
              MT5
            </span>
          </DialogTitle>
          <DialogDescription className="text-[11px] text-muted-foreground">
            Attach Eclipse to a running MetaTrader 5 terminal. No password is stored;
            the terminal must already be logged in.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="space-y-4">
          <div className="flex items-center justify-between gap-2 rounded-xl border border-border/20 px-3 py-2">
            <div>
              <p className="text-xs font-medium text-foreground">MetaTrader 5 bridge</p>
              <p className="text-[10px] text-muted-foreground">
                {mt5?.available
                  ? "Ready — enable Algo Trading in MT5 before placing orders."
                  : mt5?.unavailableReason ?? "Checking the runtime…"}
              </p>
            </div>
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide",
                !mt5
                  ? "border-border/30 bg-white/[0.04] text-muted-foreground"
                  : mt5.available
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                    : "border-amber-500/30 bg-amber-500/10 text-amber-300",
              )}
            >
              {!mt5 ? "checking" : mt5.available ? "ready" : "unavailable"}
            </span>
          </div>

          {error && <p className="text-[11px] text-rose-300">{error}</p>}
          {notice && <p className="text-[11px] text-emerald-300">{notice}</p>}

          {loading ? (
            <p className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <Loader2 size={13} className="animate-spin" /> Reading the broker…
            </p>
          ) : connection ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-border/20 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-foreground">
                    {connection.label} · {connection.kind.toUpperCase()}
                  </p>
                  {account && (
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase",
                        account.mode === "real"
                          ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
                          : "border-sky-500/30 bg-sky-500/10 text-sky-300",
                      )}
                    >
                      {account.mode}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  {connection.status}
                  {connection.statusReason ? ` — ${connection.statusReason}` : ""}
                </p>
                {account && (
                  <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
                    <span className="text-muted-foreground">
                      Account <span className="font-mono text-foreground">{account.login}</span>
                    </span>
                    <span className="text-muted-foreground">
                      {account.server || "—"}
                    </span>
                    <span className="text-muted-foreground">
                      Balance{" "}
                      <span className="font-mono text-foreground">
                        {account.balance.toLocaleString()} {account.currency}
                      </span>
                    </span>
                    <span className="text-muted-foreground">
                      Equity{" "}
                      <span className="font-mono text-foreground">
                        {account.equity.toLocaleString()}
                      </span>
                    </span>
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="flex-1"
                  onClick={test}
                  disabled={busy !== null}
                >
                  {busy === "test" ? <Loader2 size={12} className="animate-spin" /> : null}
                  Test
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="flex-1"
                  onClick={sync}
                  disabled={busy !== null}
                >
                  {busy === "sync" ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <RefreshCw size={12} />
                  )}
                  Sync
                </Button>
              </div>
              <button
                type="button"
                onClick={() => setShowForm((value) => !value)}
                className="text-[10px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                {showForm ? "Hide connection form" : "Add another connection"}
              </button>
            </div>
          ) : null}

          {(showForm || !connection) && (
            <div className="space-y-3 rounded-xl border border-border/20 p-3">
              <p className="text-xs font-medium text-foreground">Connect MetaTrader 5</p>
              <div className="grid grid-cols-2 gap-2">
                <label className="col-span-2 space-y-1">
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Label</span>
                  <input value={label} onChange={(event) => setLabel(event.target.value)} className={inputClass} />
                </label>
                <label className="space-y-1">
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Mode</span>
                  <select
                    value={mode}
                    onChange={(event) => setMode(event.target.value === "live" ? "live" : "demo")}
                    className={inputClass}
                  >
                    <option value="demo">Demo</option>
                    <option value="live">Live (arm in Settings)</option>
                  </select>
                </label>
                <label className="space-y-1">
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Magic</span>
                  <input value={magic} onChange={(event) => setMagic(event.target.value)} className={inputClass} />
                </label>
                <label className="col-span-2 space-y-1">
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Terminal path</span>
                  <input
                    value={terminalPath}
                    onChange={(event) => setTerminalPath(event.target.value)}
                    className={inputClass}
                  />
                </label>
                <label className="col-span-2 space-y-1">
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
                    Max margin (live only)
                  </span>
                  <input
                    value={maxMargin}
                    onChange={(event) => setMaxMargin(event.target.value)}
                    className={inputClass}
                  />
                </label>
              </div>
              <Button
                type="button"
                size="sm"
                className="w-full"
                onClick={add}
                disabled={busy === "create"}
              >
                {busy === "create" ? <Loader2 size={12} className="animate-spin" /> : <Handshake size={12} />}
                Add &amp; test connection
              </Button>
            </div>
          )}

          <p className="text-[10px] text-muted-foreground">
            Live arming, limits and mandates live in <span className="font-medium text-foreground">Settings → Broker connection</span>.
            Eclipse never stores your MT5 password.
          </p>
        </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
