"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import {
  ledgerClient,
  type LedgerAccount,
  type LedgerDocument,
  type Party,
} from "@/lib/ledger/client";
import { formatMoney } from "./use-accounting";

const today = () => new Date().toISOString().slice(0, 10);

export function DocumentsPanel({
  ledgerId,
  accounts,
}: {
  ledgerId: string;
  accounts: LedgerAccount[];
}) {
  const [kind, setKind] = useState<"INVOICE" | "BILL">("INVOICE");
  const [documents, setDocuments] = useState<LedgerDocument[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [taxCodes, setTaxCodes] = useState<Array<{ code: string; rate: string }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    partyId: "",
    accountCode: "",
    amount: "",
    taxCode: "",
    description: "",
    date: today(),
  });
  const [payFor, setPayFor] = useState<LedgerDocument | null>(null);
  const [payAmount, setPayAmount] = useState("");
  const [bank, setBank] = useState("");

  const cashAccounts = useMemo(() => accounts.filter((account) => account.isCash), [accounts]);
  const lineAccounts = useMemo(
    () =>
      accounts.filter((account) =>
        kind === "INVOICE" ? account.type === "REVENUE" : account.type === "EXPENSE",
      ),
    [accounts, kind],
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const [docs, people, codes] = await Promise.all([
        ledgerClient.documents(ledgerId, kind),
        ledgerClient.parties(ledgerId, kind === "INVOICE" ? "CUSTOMER" : "VENDOR"),
        ledgerClient.taxCodes(ledgerId),
      ]);
      setDocuments(docs);
      setParties(people);
      setTaxCodes(codes);
      setForm((previous) => ({
        ...previous,
        partyId: people[0]?.id ?? "",
        accountCode: lineAccounts[0]?.code ?? "",
      }));
      setBank((previous) => previous || cashAccounts[0]?.code || "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not load documents");
    }
  }, [ledgerId, kind, lineAccounts, cashAccounts]);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      await ledgerClient.createDocument(ledgerId, {
        kind,
        party_id: form.partyId,
        issue_date: form.date,
        lines: [
          {
            account_code: form.accountCode,
            unit_price: form.amount,
            tax_code: form.taxCode || undefined,
            description: form.description || undefined,
          },
        ],
      });
      setForm((previous) => ({ ...previous, amount: "", description: "" }));
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not create the document");
    } finally {
      setBusy(false);
    }
  };

  const pay = async () => {
    if (!payFor) return;
    setBusy(true);
    setError(null);
    try {
      await ledgerClient.payDocument(ledgerId, payFor.id, {
        date: today(),
        amount: payAmount || payFor.outstanding,
        bank_account: bank,
      });
      setPayFor(null);
      setPayAmount("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not record the payment");
    } finally {
      setBusy(false);
    }
  };

  const ready = form.partyId && form.accountCode && Number(form.amount) > 0;

  return (
    <div className="space-y-3">
      {error ? (
        <div className="glass-card rounded-xl border border-red-500/30 p-3 text-xs text-red-300">
          {error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-end gap-2">
        {(["INVOICE", "BILL"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setKind(value)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs",
              kind === value
                ? "glass-card text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {value === "INVOICE" ? "Invoices (AR)" : "Bills (AP)"}
          </button>
        ))}
        <span className="ml-auto text-[11px] text-muted-foreground">
          {documents.length} document(s)
        </span>
      </div>

      <div className="glass-card grid gap-2 rounded-xl p-3 md:grid-cols-6">
        <select
          value={form.partyId}
          onChange={(event) => setForm({ ...form, partyId: event.target.value })}
          className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
        >
          <option value="">
            {kind === "INVOICE" ? "Customer…" : "Vendor…"}
          </option>
          {parties.map((party) => (
            <option key={party.id} value={party.id}>
              {party.name}
            </option>
          ))}
        </select>
        <select
          value={form.accountCode}
          onChange={(event) => setForm({ ...form, accountCode: event.target.value })}
          className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
        >
          {lineAccounts.map((account) => (
            <option key={account.code} value={account.code}>
              {account.code} {account.name}
            </option>
          ))}
        </select>
        <input
          value={form.description}
          placeholder="Description"
          onChange={(event) => setForm({ ...form, description: event.target.value })}
          className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
        />
        <input
          value={form.amount}
          placeholder="Amount"
          inputMode="decimal"
          onChange={(event) => setForm({ ...form, amount: event.target.value })}
          className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 font-mono text-xs text-foreground"
        />
        <select
          value={form.taxCode}
          onChange={(event) => setForm({ ...form, taxCode: event.target.value })}
          className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
        >
          <option value="">No tax</option>
          {taxCodes.map((code) => (
            <option key={code.code} value={code.code}>
              {code.code} ({(Number(code.rate) * 100).toFixed(0)}%)
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy || !ready}
          onClick={() => void create()}
          className="rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background disabled:opacity-40"
        >
          {busy ? "Posting…" : `Post ${kind === "INVOICE" ? "invoice" : "bill"}`}
        </button>
      </div>

      {parties.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">
          No {kind === "INVOICE" ? "customers" : "vendors"} yet — ask the Bookkeeper to create
          one (`ledger_party_create`), then reload.
        </p>
      ) : null}

      <div className="glass-card overflow-hidden rounded-xl">
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            <tr className="border-b border-white/5">
              <th className="px-3 py-2 text-left">Number</th>
              <th className="px-3 py-2 text-left">Party</th>
              <th className="px-3 py-2 text-left">Due</th>
              <th className="px-3 py-2 text-right">Total</th>
              <th className="px-3 py-2 text-right">Outstanding</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.id} className="border-b border-white/5 last:border-0">
                <td className="px-3 py-1.5 font-mono text-muted-foreground">
                  {document.number}
                </td>
                <td className="px-3 py-1.5 text-foreground">{document.partyName}</td>
                <td className="px-3 py-1.5 font-mono text-muted-foreground">
                  {document.dueDate}
                </td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums text-foreground">
                  {formatMoney(document.total)}
                </td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums text-foreground">
                  {formatMoney(document.outstanding)}
                </td>
                <td className="px-3 py-1.5 text-[10px] uppercase text-muted-foreground">
                  {document.status.replace("_", " ")}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {document.status !== "PAID" && document.status !== "VOID" ? (
                    <button
                      type="button"
                      onClick={() => {
                        setPayFor(document);
                        setPayAmount(document.outstanding);
                      }}
                      className="rounded px-2 py-0.5 text-[10px] text-muted-foreground hover:text-foreground"
                    >
                      Pay
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
            {documents.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-muted-foreground">
                  Nothing yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {payFor ? (
        <div className="glass-card flex flex-wrap items-center gap-2 rounded-xl p-3">
          <span className="text-xs text-foreground">
            Pay {payFor.number} — outstanding {formatMoney(payFor.outstanding)}
          </span>
          <input
            value={payAmount}
            inputMode="decimal"
            onChange={(event) => setPayAmount(event.target.value)}
            className="w-28 rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 font-mono text-xs text-foreground"
          />
          <select
            value={bank}
            onChange={(event) => setBank(event.target.value)}
            className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
          >
            {cashAccounts.map((account) => (
              <option key={account.code} value={account.code}>
                {account.code} {account.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !bank}
            onClick={() => void pay()}
            className="rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background disabled:opacity-40"
          >
            {busy ? "Posting…" : "Record payment"}
          </button>
          <button
            type="button"
            onClick={() => setPayFor(null)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
        </div>
      ) : null}
    </div>
  );
}
