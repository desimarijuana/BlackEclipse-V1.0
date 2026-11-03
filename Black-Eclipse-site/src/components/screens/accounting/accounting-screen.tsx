"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { ConsolidationPanel } from "./consolidation-panel";
import { DocumentsPanel } from "./documents-panel";
import { formatMoney, useAccounting } from "./use-accounting";

type Section = "trial" | "pnl" | "journal" | "close" | "ar" | "documents" | "groups";

const SECTION_LABEL: Record<Section, string> = {
  trial: "Trial balance",
  pnl: "P&L",
  journal: "Journal",
  close: "Close",
  ar: "Receivables",
  documents: "Invoices & bills",
  groups: "Consolidation",
};

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="glass-card rounded-xl p-4">
      <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 font-mono text-xl tabular-nums text-foreground">{value}</div>
      {hint ? <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

function CheckBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
        ok
          ? "bg-emerald-500/10 text-emerald-400"
          : "bg-red-500/10 text-red-400",
      )}
    >
      {ok ? "✓" : "!"} {label}
    </span>
  );
}

function EmptyState({
  onCreate,
  busy,
}: {
  onCreate: (name: string, currency: string) => Promise<string | null>;
  busy: boolean;
}) {
  const [name, setName] = useState("My books");
  const [currency, setCurrency] = useState("USD");
  return (
    <div className="glass-card mx-auto mt-10 max-w-md rounded-2xl p-6">
      <h2 className="text-sm font-semibold text-foreground">Start a book of record</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        A ledger installs a chart of accounts. Every posting after that is balanced or
        refused — the engine never keeps a half-posted entry.
      </p>
      <label className="mt-4 block text-[11px] text-muted-foreground">
        Name
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-foreground outline-none focus:border-white/25"
        />
      </label>
      <label className="mt-3 block text-[11px] text-muted-foreground">
        Base currency
        <input
          value={currency}
          maxLength={3}
          onChange={(event) => setCurrency(event.target.value.toUpperCase())}
          className="mt-1 w-24 rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-sm uppercase text-foreground outline-none focus:border-white/25"
        />
      </label>
      <button
        type="button"
        disabled={busy || !name.trim()}
        onClick={() => void onCreate(name.trim(), currency)}
        className="mt-4 w-full rounded-lg bg-foreground px-3 py-2 text-sm font-medium text-background disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create ledger"}
      </button>
    </div>
  );
}

export function AccountingScreen() {
  const accounting = useAccounting();
  const [section, setSection] = useState<Section>("trial");

  if (accounting.loading && !accounting.ledger) {
    return (
      <div className="space-y-3 p-6">
        {[0, 1, 2].map((key) => (
          <div key={key} className="glass-card h-20 animate-pulse rounded-xl" />
        ))}
      </div>
    );
  }

  if (!accounting.ledger) {
    return (
      <div className="p-6">
        {accounting.error ? (
          <div className="glass-card mx-auto mb-4 max-w-md rounded-xl border border-red-500/30 p-3 text-xs text-red-300">
            {accounting.error}
          </div>
        ) : null}
        <EmptyState onCreate={accounting.createLedger} busy={accounting.busy} />
      </div>
    );
  }

  const sheet = accounting.sheet;
  const pnl = accounting.pnl;
  const trial = accounting.trial;
  const aging = accounting.aging;

  return (
    <div className="space-y-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Accounting</h1>
          <p className="text-xs text-muted-foreground">
            {accounting.ledger.name} · {accounting.ledger.baseCurrency} ·{" "}
            {accounting.ledger.summary?.entryCount ?? 0} entries
            {accounting.ledger.summary?.currentPeriod
              ? ` · period ${accounting.ledger.summary.currentPeriod.startDate} → ${accounting.ledger.summary.currentPeriod.endDate}`
              : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={accounting.ledger.id}
            onChange={(event) => accounting.selectLedger(event.target.value)}
            className="glass-card-subtle rounded-lg px-3 py-2 text-sm text-foreground outline-none"
          >
            {accounting.ledgers.map((ledger) => (
              <option key={ledger.id} value={ledger.id}>
                {ledger.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void accounting.reload()}
            className="glass-card-subtle rounded-lg px-3 py-2 text-xs text-muted-foreground hover:text-foreground"
          >
            Refresh
          </button>
        </div>
      </header>

      {accounting.error ? (
        <div className="glass-card rounded-xl border border-red-500/30 p-3 text-xs text-red-300">
          {accounting.error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Assets" value={formatMoney(sheet?.assets.total)} />
        <Stat label="Liabilities" value={formatMoney(sheet?.liabilities.total)} />
        <Stat
          label="Equity"
          value={formatMoney(sheet?.equity.total)}
          hint={sheet ? `incl. earnings ${formatMoney(sheet.currentEarnings)}` : undefined}
        />
        <Stat label="Net income" value={formatMoney(pnl?.netIncome)} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(Object.keys(SECTION_LABEL) as Section[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              setSection(key);
              if (key === "ar" && !accounting.aging) void accounting.refreshAging("AR");
            }}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs transition",
              section === key
                ? "glass-card text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {SECTION_LABEL[key]}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          {trial ? <CheckBadge ok={trial.balanced} label="trial balance" /> : null}
          {sheet ? <CheckBadge ok={sheet.balanced} label="equation" /> : null}
          {aging ? <CheckBadge ok={aging.reconciled} label="AR ↔ control" /> : null}
        </div>
      </div>

      {section === "trial" ? (
        <div className="glass-card overflow-hidden rounded-xl">
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              <tr className="border-b border-white/5">
                <th className="px-3 py-2 text-left">Code</th>
                <th className="px-3 py-2 text-left">Account</th>
                <th className="px-3 py-2 text-right">Debit</th>
                <th className="px-3 py-2 text-right">Credit</th>
              </tr>
            </thead>
            <tbody>
              {(trial?.rows ?? []).map((row) => (
                <tr key={row.code} className="border-b border-white/5 last:border-0">
                  <td className="px-3 py-1.5 font-mono text-muted-foreground">{row.code}</td>
                  <td className="px-3 py-1.5 text-foreground">{row.name}</td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums text-foreground">
                    {row.closingDebit === "0.00000000" ? "" : formatMoney(row.closingDebit)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums text-foreground">
                    {row.closingCredit === "0.00000000" ? "" : formatMoney(row.closingCredit)}
                  </td>
                </tr>
              ))}
              {!trial || trial.rows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">
                    No postings yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}

      {section === "pnl" ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {[
            { title: "Revenue", section: pnl?.revenue },
            { title: "Cost of sales", section: pnl?.costOfSales },
            { title: "Operating expenses", section: pnl?.operatingExpenses },
            { title: "Depreciation", section: pnl?.depreciation },
          ].map(({ title, section: block }) => (
            <div key={title} className="glass-card rounded-xl p-4">
              <div className="flex items-baseline justify-between">
                <h3 className="text-xs font-semibold text-foreground">{title}</h3>
                <span className="font-mono text-xs tabular-nums text-muted-foreground">
                  {formatMoney(block?.total)}
                </span>
              </div>
              <ul className="mt-2 space-y-1">
                {(block?.rows ?? []).map((row) => (
                  <li key={row.code} className="flex justify-between text-[11px]">
                    <span className="text-muted-foreground">
                      <span className="mr-2 font-mono">{row.code}</span>
                      {row.name}
                    </span>
                    <span className="font-mono tabular-nums text-foreground">
                      {formatMoney(row.amount)}
                    </span>
                  </li>
                ))}
                {!block || block.rows.length === 0 ? (
                  <li className="text-[11px] text-muted-foreground">—</li>
                ) : null}
              </ul>
            </div>
          ))}
        </div>
      ) : null}

      {section === "journal" ? (
        <div className="glass-card overflow-hidden rounded-xl">
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              <tr className="border-b border-white/5">
                <th className="px-3 py-2 text-left">#</th>
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-left">Memo</th>
                <th className="px-3 py-2 text-left">Source</th>
                <th className="px-3 py-2 text-right">Debit</th>
                <th className="px-3 py-2 text-right">Credit</th>
              </tr>
            </thead>
            <tbody>
              {accounting.entries.map((entry) => (
                <tr key={entry.id} className="border-b border-white/5 last:border-0">
                  <td className="px-3 py-1.5 font-mono text-muted-foreground">
                    {entry.entryNo}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-muted-foreground">
                    {entry.entryDate}
                  </td>
                  <td className="px-3 py-1.5 text-foreground">{entry.memo || "—"}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{entry.source}</td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums text-foreground">
                    {formatMoney(entry.totalDebit)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums text-foreground">
                    {formatMoney(entry.totalCredit)}
                  </td>
                </tr>
              ))}
              {accounting.entries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                    No entries yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}

      {section === "close" ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              A blocker refuses the close; a warning is the operator&apos;s to accept.
            </p>
            <button
              type="button"
              disabled={accounting.busy}
              onClick={() => void accounting.runClose()}
              className="glass-card rounded-lg px-3 py-2 text-xs font-medium text-foreground disabled:opacity-50"
            >
              {accounting.busy ? "Checking…" : "Run close check"}
            </button>
          </div>
          {accounting.close ? (
            <div className="glass-card rounded-xl p-4">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase",
                    accounting.close.status === "READY"
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-red-500/10 text-red-400",
                  )}
                >
                  {accounting.close.status}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {accounting.close.startDate} → {accounting.close.endDate} ·{" "}
                  {accounting.close.blockerCount} blocker(s) ·{" "}
                  {accounting.close.warningCount} warning(s)
                </span>
              </div>
              <ul className="mt-3 space-y-2">
                {accounting.close.findings.map((finding, index) => (
                  <li key={`${finding.code}-${index}`} className="flex gap-2 text-[11px]">
                    <span
                      className={cn(
                        "mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase",
                        finding.severity === "blocker"
                          ? "bg-red-500/10 text-red-400"
                          : "bg-amber-500/10 text-amber-400",
                      )}
                    >
                      {finding.severity}
                    </span>
                    <span className="text-muted-foreground">
                      <span className="font-mono text-foreground">{finding.code}</span>{" "}
                      {finding.detail}
                    </span>
                  </li>
                ))}
                {accounting.close.findings.length === 0 ? (
                  <li className="text-[11px] text-emerald-400">No findings.</li>
                ) : null}
              </ul>
            </div>
          ) : (
            <div className="glass-card rounded-xl p-6 text-center text-xs text-muted-foreground">
              Run the close check to see blockers and warnings for the current period.
            </div>
          )}
        </div>
      ) : null}

      {section === "ar" ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            {Object.entries(aging?.buckets ?? {}).map(([bucket, amount]) => (
              <Stat key={bucket} label={bucket} value={formatMoney(amount)} />
            ))}
          </div>
          <div className="glass-card overflow-hidden rounded-xl">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                <tr className="border-b border-white/5">
                  <th className="px-3 py-2 text-left">Customer</th>
                  <th className="px-3 py-2 text-right">Documents</th>
                  <th className="px-3 py-2 text-right">Oldest (days)</th>
                  <th className="px-3 py-2 text-right">Outstanding</th>
                </tr>
              </thead>
              <tbody>
                {(aging?.parties ?? []).map((party) => (
                  <tr key={party.partyId} className="border-b border-white/5 last:border-0">
                    <td className="px-3 py-1.5 text-foreground">{party.partyName}</td>
                    <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted-foreground">
                      {party.documents}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted-foreground">
                      {party.oldestDays}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono tabular-nums text-foreground">
                      {formatMoney(party.outstanding)}
                    </td>
                  </tr>
                ))}
                {!aging || aging.parties.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">
                      Nothing outstanding.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {aging && !aging.reconciled ? (
            <p className="text-[11px] text-amber-400">
              Open items differ from control account {aging.controlAccount} by{" "}
              {formatMoney(aging.difference)} — a manual posting to the control account is
              the usual cause.
            </p>
          ) : null}
        </div>
      ) : null}

      {section === "documents" ? (
        <DocumentsPanel ledgerId={accounting.ledger.id} accounts={accounting.accounts} />
      ) : null}

      {section === "groups" ? (
        <ConsolidationPanel
          ledgers={accounting.ledgers}
          currentLedgerId={accounting.ledger.id}
        />
      ) : null}
    </div>
  );
}
