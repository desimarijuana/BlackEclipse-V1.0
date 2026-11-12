"use client";

// The broker connection form. Extracted from the dialog so the shell stays
// readable and under the source size budget.

import { Handshake, Loader2 } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BROKER_RESPONSIBILITY_NOTICE } from "@/lib/legal/disclosure";

export type BrokerKindId = "mt5" | "mt4_bridge" | "alpaca" | "ibkr";

export const inputClass =
  "w-full rounded-xl border border-border/40 bg-transparent px-2.5 py-1.5 text-xs text-foreground focus:border-primary/40 focus:outline-none";

export function ConnectionForm({
  kind,
  setKind,
  allowKindChange,
  label,
  setLabel,
  mode,
  setMode,
  terminalPath,
  setTerminalPath,
  bridgeUrl,
  setBridgeUrl,
  bridgeSecretRef,
  setBridgeSecretRef,
  baseUrl,
  setBaseUrl,
  dataUrl,
  setDataUrl,
  credentialRef,
  setCredentialRef,
  brokerAccountId,
  setBrokerAccountId,
  magic,
  setMagic,
  maxMargin,
  setMaxMargin,
  busy,
  onSubmit,
  submitLabel,
  compact = false,
}: {
  kind: BrokerKindId;
  setKind: (value: BrokerKindId) => void;
  allowKindChange: boolean;
  label: string;
  setLabel: (value: string) => void;
  mode: "demo" | "live";
  setMode: (value: "demo" | "live") => void;
  terminalPath: string;
  setTerminalPath: (value: string) => void;
  bridgeUrl: string;
  setBridgeUrl: (value: string) => void;
  bridgeSecretRef: string;
  setBridgeSecretRef: (value: string) => void;
  baseUrl: string;
  setBaseUrl: (value: string) => void;
  dataUrl: string;
  setDataUrl: (value: string) => void;
  credentialRef: string;
  setCredentialRef: (value: string) => void;
  brokerAccountId: string;
  setBrokerAccountId: (value: string) => void;
  magic: string;
  setMagic: (value: string) => void;
  maxMargin: string;
  setMaxMargin: (value: string) => void;
  busy: boolean;
  onSubmit: () => void;
  submitLabel: string;
  compact?: boolean;
}) {
  const isBridge = kind === "mt4_bridge";
  const isMt5 = kind === "mt5";
  const isAlpaca = kind === "alpaca";
  const isIbkr = kind === "ibkr";
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <label className="col-span-2 space-y-1">
          <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Broker type</span>
          {allowKindChange ? (
            <Select
              value={kind}
              onValueChange={(value) =>
                setKind(
                  value === "mt4_bridge" || value === "alpaca" || value === "ibkr"
                    ? value
                    : "mt5",
                )
              }
            >
              <SelectTrigger className={cn(inputClass, "h-auto w-full justify-between py-1.5")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="min-w-[var(--anchor-width)]">
                <SelectItem value="mt5">MetaTrader 5 (local terminal)</SelectItem>
                <SelectItem value="mt4_bridge">MetaTrader 4 (HTTP bridge, read-only)</SelectItem>
                <SelectItem value="alpaca">Alpaca (REST, read-only)</SelectItem>
                <SelectItem value="ibkr">Interactive Brokers (gateway, read-only)</SelectItem>
              </SelectContent>
            </Select>
          ) : (
            <p className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 font-mono text-[11px] text-muted-foreground">
              {isBridge
                ? "MetaTrader 4 (HTTP bridge, read-only)"
                : isAlpaca
                  ? "Alpaca (REST, read-only)"
                  : isIbkr
                    ? "Interactive Brokers (gateway, read-only)"
                    : "MetaTrader 5 (local terminal)"}
            </p>
          )}
        </label>
        <label className="col-span-2 space-y-1">
          <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Label</span>
          <input value={label} onChange={(event) => setLabel(event.target.value)} className={inputClass} />
        </label>
        <label className="space-y-1">
          <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Mode</span>
          <Select
            value={mode}
            onValueChange={(value) => setMode(value === "live" ? "live" : "demo")}
          >
            <SelectTrigger className={cn(inputClass, "h-auto w-full justify-between py-1.5")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="min-w-[var(--anchor-width)]">
              <SelectItem value="demo">Demo</SelectItem>
              <SelectItem value="live">Live (arm in Settings)</SelectItem>
            </SelectContent>
          </Select>
        </label>
        {(isMt5 || isBridge) && (
          <label className="space-y-1">
            <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Magic</span>
            <input value={magic} onChange={(event) => setMagic(event.target.value)} className={inputClass} />
          </label>
        )}
        {isBridge && (
          <>
            <label className="col-span-2 space-y-1">
              <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
                Bridge URL
              </span>
              <input
                value={bridgeUrl}
                onChange={(event) => setBridgeUrl(event.target.value)}
                placeholder="http://127.0.0.1:8090"
                className={inputClass}
              />
            </label>
            <label className="col-span-2 space-y-1">
              <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
                Secret name (env var or secret:// ref, optional)
              </span>
              <input
                value={bridgeSecretRef}
                onChange={(event) => setBridgeSecretRef(event.target.value)}
                placeholder="MT4_BRIDGE_TOKEN"
                className={inputClass}
              />
            </label>
          </>
        )}
        {isMt5 && (
          <>
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
          </>
        )}
        {(isAlpaca || isIbkr) && (
          <>
            <label className="col-span-2 space-y-1">
              <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
                {isAlpaca ? "Trading base URL" : "Client Portal gateway URL"}
              </span>
              <input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder={
                  isAlpaca ? "https://paper-api.alpaca.markets" : "https://localhost:5000/v1/api"
                }
                className={inputClass}
              />
            </label>
            {isAlpaca && (
              <label className="col-span-2 space-y-1">
                <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
                  Market-data base URL
                </span>
                <input
                  value={dataUrl}
                  onChange={(event) => setDataUrl(event.target.value)}
                  placeholder="https://data.alpaca.markets"
                  className={inputClass}
                />
              </label>
            )}
            {isIbkr && (
              <label className="col-span-2 space-y-1">
                <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
                  IBKR account id
                </span>
                <input
                  value={brokerAccountId}
                  onChange={(event) => setBrokerAccountId(event.target.value)}
                  placeholder="DU1234567"
                  className={inputClass}
                />
              </label>
            )}
            <label className="col-span-2 space-y-1">
              <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
                Credential name (env var or secret:// ref)
              </span>
              <input
                value={credentialRef}
                onChange={(event) => setCredentialRef(event.target.value)}
                placeholder={isAlpaca ? "ALPACA_KEYS" : "IBKR_GATEWAY_COOKIE"}
                className={inputClass}
              />
            </label>
          </>
        )}
      </div>
      {!compact && (
        <p className="text-[9.5px] text-muted-foreground">
          {isBridge ? (
            <>
              The bridge runs next to MT4 and owns the login. Eclipse only reads the documented
              JSON contract and never places an order through it. Point it at loopback.
            </>
          ) : isAlpaca || isIbkr ? (
            <>
              Read-only. The credential is a NAME (env var or secret:// ref), never a value. Journal
              P&amp;L for these brokers is FIFO-computed from executions; the smoke test proves the
              live contract before you rely on it.
            </>
          ) : (
            <>
              No password is stored: Eclipse attaches to the account already logged into the terminal.
              Enable <span className="font-medium text-foreground">Algo Trading</span> in MT5 before
              placing any order.
            </>
          )}
        </p>
      )}
      {!compact && (
        <p className="text-[9.5px] leading-relaxed text-muted-foreground/70">
          {BROKER_RESPONSIBILITY_NOTICE}
        </p>
      )}
      <Button type="button" size="sm" className="w-full" onClick={onSubmit} disabled={busy}>
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Handshake size={12} />}
        {submitLabel}
      </Button>
    </div>
  );
}
