"use client";

import { useCallback, useEffect, useState } from "react";
import {
  LedgerRequestError,
  ledgerClient,
  type AgingReport,
  type BalanceSheet,
  type CloseReport,
  type IncomeStatement,
  type JournalEntrySummary,
  type LedgerAccount,
  type LedgerSummary,
  type TrialBalance,
} from "@/lib/ledger/client";

export interface AccountingState {
  ledgers: LedgerSummary[];
  ledger: LedgerSummary | null;
  accounts: LedgerAccount[];
  trial: TrialBalance | null;
  sheet: BalanceSheet | null;
  pnl: IncomeStatement | null;
  entries: JournalEntrySummary[];
  close: CloseReport | null;
  aging: AgingReport | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
}

const INITIAL: AccountingState = {
  ledgers: [],
  ledger: null,
  accounts: [],
  trial: null,
  sheet: null,
  pnl: null,
  entries: [],
  close: null,
  aging: null,
  loading: true,
  busy: false,
  error: null,
};

const message = (error: unknown, fallback: string): string =>
  error instanceof LedgerRequestError
    ? error.message
    : error instanceof Error
      ? error.message
      : fallback;

/** `"1234.56789000"` → `"1,234.57"`; a malformed value is shown verbatim. */
export function formatMoney(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const text = String(value);
  const negative = text.startsWith("-");
  const [whole, fraction = ""] = (negative ? text.slice(1) : text).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const cents = (fraction + "00").slice(0, 2);
  return `${negative ? "-" : ""}${grouped}.${cents}`;
}

export function useAccounting() {
  const [state, setState] = useState<AccountingState>(INITIAL);

  const load = useCallback(async (ledgerId: string | null) => {
    if (!ledgerId) {
      setState((previous) => ({ ...previous, loading: false, ledger: null }));
      return;
    }
    setState((previous) => ({ ...previous, loading: true, error: null }));
    try {
      const [ledger, accounts, trial, sheet, pnl, entries, aging] = await Promise.all([
        ledgerClient.get(ledgerId),
        ledgerClient.accountsDetailed(ledgerId),
        ledgerClient.trialBalance(ledgerId),
        ledgerClient.balanceSheet(ledgerId),
        ledgerClient.incomeStatement(ledgerId),
        ledgerClient.entries(ledgerId, { limit: 50 }),
        ledgerClient.aging(ledgerId, "AR"),
      ]);
      setState((previous) => ({
        ...previous,
        ledger,
        accounts,
        trial,
        sheet,
        pnl,
        entries,
        aging,
        loading: false,
      }));
    } catch (error) {
      setState((previous) => ({
        ...previous,
        loading: false,
        error: message(error, "could not load the ledger"),
      }));
    }
  }, []);

  const refreshLedgers = useCallback(
    async (preferredId?: string | null) => {
      try {
        const ledgers = await ledgerClient.list();
        setState((previous) => ({ ...previous, ledgers }));
        await load(preferredId ?? ledgers[0]?.id ?? null);
      } catch (error) {
        setState((previous) => ({
          ...previous,
          loading: false,
          error: message(error, "could not list ledgers"),
        }));
      }
    },
    [load],
  );

  useEffect(() => {
    void refreshLedgers();
  }, [refreshLedgers]);

  const createLedger = useCallback(
    async (name: string, baseCurrency: string) => {
      setState((previous) => ({ ...previous, busy: true, error: null }));
      try {
        const created = (await ledgerClient.create({
          name,
          base_currency: baseCurrency,
        })) as { id: string };
        await refreshLedgers(created.id);
        return created.id;
      } catch (error) {
        setState((previous) => ({
          ...previous,
          error: message(error, "could not create the ledger"),
        }));
        return null;
      } finally {
        setState((previous) => ({ ...previous, busy: false }));
      }
    },
    [refreshLedgers],
  );

  const selectLedger = useCallback((id: string) => void load(id), [load]);

  const runClose = useCallback(async () => {
    if (!state.ledger) return;
    setState((previous) => ({ ...previous, busy: true, error: null }));
    try {
      const close = await ledgerClient.closePreview(state.ledger.id);
      setState((previous) => ({ ...previous, close, busy: false }));
    } catch (error) {
      setState((previous) => ({
        ...previous,
        busy: false,
        error: message(error, "close check failed"),
      }));
    }
  }, [state.ledger]);

  const refreshAging = useCallback(
    async (kind: "AR" | "AP") => {
      if (!state.ledger) return;
      try {
        const aging = await ledgerClient.aging(state.ledger.id, kind);
        setState((previous) => ({ ...previous, aging }));
      } catch (error) {
        setState((previous) => ({ ...previous, error: message(error, "aging failed") }));
      }
    },
    [state.ledger],
  );

  return {
    ...state,
    createLedger,
    selectLedger,
    runClose,
    refreshAging,
    reload: () => load(state.ledger?.id ?? null),
  };
}
