"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import {
  ledgerClient,
  type ConsolidationReport,
  type LedgerGroup,
  type LedgerSummary,
} from "@/lib/ledger/client";
import { formatMoney } from "./use-accounting";

export function ConsolidationPanel({
  ledgers,
  currentLedgerId,
}: {
  ledgers: LedgerSummary[];
  currentLedgerId: string;
}) {
  const [groups, setGroups] = useState<LedgerGroup[]>([]);
  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [report, setReport] = useState<ConsolidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newGroup, setNewGroup] = useState("");
  const [memberId, setMemberId] = useState(currentLedgerId);
  const [memberPct, setMemberPct] = useState("100");

  const load = useCallback(async () => {
    try {
      const rows = await ledgerClient.groups();
      setGroups(rows);
      setActiveGroupId((previous) => previous ?? rows[0]?.id ?? null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not load groups");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const activeGroup = groups.find((group) => group.id === activeGroupId) ?? null;

  const createGroup = async () => {
    if (!newGroup.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await ledgerClient.createGroup({
        name: newGroup.trim(),
        base_currency: "USD",
      });
      setNewGroup("");
      await load();
      setActiveGroupId(created.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not create the group");
    } finally {
      setBusy(false);
    }
  };

  const addMember = async () => {
    if (!activeGroup) return;
    setBusy(true);
    setError(null);
    try {
      await ledgerClient.addGroupMember(activeGroup.id, {
        ledger_id: memberId,
        ownership_pct: memberPct,
      });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not add the member");
    } finally {
      setBusy(false);
    }
  };

  const consolidate = async () => {
    if (!activeGroup) return;
    setBusy(true);
    setError(null);
    try {
      setReport(
        await ledgerClient.consolidate(activeGroup.id, {
          as_of: new Date().toISOString().slice(0, 10),
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "consolidation failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      {error ? (
        <div className="glass-card rounded-xl border border-red-500/30 p-3 text-xs text-red-300">
          {error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {groups.map((group) => (
          <button
            key={group.id}
            type="button"
            onClick={() => {
              setActiveGroupId(group.id);
              setReport(null);
            }}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs",
              activeGroupId === group.id
                ? "glass-card text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {group.name} · {group.members.length}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <input
            value={newGroup}
            placeholder="New group name"
            onChange={(event) => setNewGroup(event.target.value)}
            className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
          />
          <button
            type="button"
            disabled={busy || !newGroup.trim()}
            onClick={() => void createGroup()}
            className="rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background disabled:opacity-40"
          >
            Create group
          </button>
        </div>
      </div>

      {activeGroup ? (
        <div className="glass-card flex flex-wrap items-center gap-2 rounded-xl p-3">
          <select
            value={memberId}
            onChange={(event) => setMemberId(event.target.value)}
            className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
          >
            {ledgers.map((ledger) => (
              <option key={ledger.id} value={ledger.id}>
                {ledger.name}
              </option>
            ))}
          </select>
          <input
            value={memberPct}
            inputMode="decimal"
            onChange={(event) => setMemberPct(event.target.value)}
            className="w-20 rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 font-mono text-xs text-foreground"
            title="Ownership %"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => void addMember()}
            className="rounded-lg px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            Add member
          </button>
          <span className="ml-auto text-[11px] text-muted-foreground">
            {activeGroup.members.length} member(s) · {activeGroup.baseCurrency}
          </span>
          <button
            type="button"
            disabled={busy || activeGroup.members.length === 0}
            onClick={() => void consolidate()}
            className="rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background disabled:opacity-40"
          >
            {busy ? "Consolidating…" : "Consolidate"}
          </button>
        </div>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          Create a group, add the ledgers that belong to it, then consolidate.
        </p>
      )}

      {report ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="glass-card rounded-xl p-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                Status
              </div>
              <div
                className={cn(
                  "mt-1 text-sm font-semibold",
                  report.status === "CONSOLIDATED" ? "text-emerald-400" : "text-red-400",
                )}
              >
                {report.status}
              </div>
              <div className="text-[10px] text-muted-foreground">{report.ownershipMethod}</div>
            </div>
            <div className="glass-card rounded-xl p-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                Consolidated assets
              </div>
              <div className="mt-1 font-mono text-sm tabular-nums text-foreground">
                {formatMoney(report.balanceSheet?.assets.total)}
              </div>
            </div>
            <div className="glass-card rounded-xl p-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                Equity
              </div>
              <div className="mt-1 font-mono text-sm tabular-nums text-foreground">
                {formatMoney(report.balanceSheet?.equity.total)}
              </div>
            </div>
            <div className="glass-card rounded-xl p-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                Eliminated
              </div>
              <div className="mt-1 font-mono text-sm tabular-nums text-foreground">
                {formatMoney(report.eliminations.reduce((sum, item) => sum + Number(item.amount), 0).toFixed(8))}
              </div>
            </div>
          </div>

          {report.eliminations.some((item) => Number(item.unmatched) !== 0) ? (
            <p className="text-[11px] text-amber-400">
              An intercompany balance is unmatched; the remainder stays in the consolidated
              books and is reported, never plugged.
            </p>
          ) : null}

          <div className="glass-card rounded-xl p-4">
            <h3 className="text-xs font-semibold text-foreground">Members</h3>
            <ul className="mt-2 space-y-1">
              {report.members.map((member) => (
                <li key={member.ledgerId} className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">
                    {member.name ?? member.ledgerId} · {member.ownershipPct}%
                  </span>
                  <span className={member.included ? "text-emerald-400" : "text-red-400"}>
                    {member.included ? "included" : (member.reason ?? "excluded")}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {report.findings.length > 0 ? (
            <div className="glass-card rounded-xl p-4">
              <h3 className="text-xs font-semibold text-foreground">Findings</h3>
              <ul className="mt-2 space-y-1 text-[11px]">
                {report.findings.map((finding, index) => (
                  <li key={`${finding.code}-${index}`}>
                    <span
                      className={cn(
                        "mr-2 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase",
                        finding.severity === "blocker"
                          ? "bg-red-500/10 text-red-400"
                          : "bg-amber-500/10 text-amber-400",
                      )}
                    >
                      {finding.severity}
                    </span>
                    <span className="text-muted-foreground">{finding.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
