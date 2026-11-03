/**
 * Browser client for the ledger front door (`/api/ledger/*`).
 *
 * It carries NO accounting logic: the Python engine owns the book, the rules and
 * the arithmetic. This is a typed call surface plus one honest error type, so a
 * refusal (`UNBALANCED_ENTRY`, `PERIOD_CLOSED`, …) reaches the UI as a message
 * rather than an empty table.
 */

export interface LedgerSummary {
  id: string;
  name: string;
  baseCurrency: string;
  ownerId: string | null;
  fiscalYearStartMonth: number;
  chartTemplate: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  summary?: {
    accountCount: number;
    periodCount: number;
    entryCount: number;
    lastEntryDate: string | null;
    currentPeriod: { startDate: string; endDate: string; status: string } | null;
  };
}

export interface TrialBalanceRow {
  code: string;
  name: string;
  type: string;
  openingDebit: string;
  openingCredit: string;
  debit: string;
  credit: string;
  closingDebit: string;
  closingCredit: string;
}

export interface StatementCheck {
  name: string;
  ok: boolean;
  detail: string;
}

export interface TrialBalance {
  startDate: string | null;
  endDate: string | null;
  rows: TrialBalanceRow[];
  totals: {
    openingDebit: string;
    openingCredit: string;
    debit: string;
    credit: string;
    closingDebit: string;
    closingCredit: string;
  };
  checks: StatementCheck[];
  balanced: boolean;
}

export interface StatementSection {
  rows: Array<{ code: string; name: string; subtype?: string; amount: string }>;
  total: string;
}

export interface BalanceSheet {
  asOf: string | null;
  assets: StatementSection;
  liabilities: StatementSection;
  equity: StatementSection;
  currentEarnings: string;
  checks: StatementCheck[];
  balanced: boolean;
}

export interface IncomeStatement {
  startDate: string | null;
  endDate: string | null;
  revenue: StatementSection;
  costOfSales: StatementSection;
  grossProfit: string;
  operatingExpenses: StatementSection;
  depreciation: StatementSection;
  totalExpenses: string;
  netIncome: string;
  checks: StatementCheck[];
  balanced: boolean;
}

export interface JournalEntrySummary {
  id: string;
  entryNo: number;
  entryDate: string;
  memo: string;
  source: string;
  status: string;
  totalDebit: string;
  totalCredit: string;
  lineCount: number;
  lines?: Array<{
    lineNo: number;
    accountCode: string;
    debit: string;
    credit: string;
    baseDebit: string;
    baseCredit: string;
    memo: string | null;
  }>;
}

export interface Finding {
  code: string;
  severity: "blocker" | "warning";
  detail: string;
  accountCode?: string;
  amount?: string;
}

export interface CloseReport {
  runId: string;
  ledgerId: string;
  periodId: string;
  startDate: string;
  endDate: string;
  status: "READY" | "BLOCKED";
  blockerCount: number;
  warningCount: number;
  entryCount: number;
  findings: Finding[];
  checks: StatementCheck[];
}

export interface AgingBucket {
  partyId: string;
  partyName: string;
  outstanding: string;
  oldestDays: number;
  documents: number;
  buckets: Record<string, string>;
}

export interface AgingReport {
  kind: "AR" | "AP";
  asOf: string;
  controlAccount: string;
  controlBalance: string;
  openTotal: string;
  difference: string;
  buckets: Record<string, string>;
  parties: AgingBucket[];
  reconciled: boolean;
}

export interface LedgerAccount {
  code: string;
  name: string;
  type: string;
  subtype?: string;
  isCash?: boolean;
  active?: boolean;
}

export interface Party {
  id: string;
  name: string;
  kind: "CUSTOMER" | "VENDOR";
  paymentTermsDays: number;
  active: boolean;
}

export interface LedgerDocument {
  id: string;
  kind: "INVOICE" | "BILL";
  number: string;
  partyId: string;
  partyName: string;
  issueDate: string;
  dueDate: string;
  subtotal: string;
  taxTotal: string;
  total: string;
  paid: string;
  outstanding: string;
  status: string;
}

export interface ConsolidationReport {
  groupId: string;
  groupName: string;
  asOf: string;
  groupCurrency: string;
  ownershipMethod: string;
  status: "CONSOLIDATED" | "BLOCKED";
  members: Array<{
    ledgerId: string;
    name?: string;
    ownershipPct: string;
    included: boolean;
    reason?: string;
  }>;
  balanceSheet: BalanceSheet | null;
  incomeStatement: IncomeStatement | null;
  eliminations: Array<{ kind: string; amount: string; matched: string; unmatched: string; balanced: boolean }>;
  findings: Finding[];
  checks: StatementCheck[];
}

export interface LedgerGroup {
  id: string;
  name: string;
  baseCurrency: string;
  members: Array<{ ledgerId: string; ownershipPct: string }>;
}

export class LedgerRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "LedgerRequestError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/ledger${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    const error = (body.error ?? {}) as Record<string, unknown>;
    throw new LedgerRequestError(
      detail || (typeof error.message === "string" ? error.message : "ledger request failed"),
      response.status,
      typeof error.code === "string" ? error.code : undefined,
    );
  }
  return body as T;
}

const today = () => new Date().toISOString().slice(0, 10);

export const ledgerClient = {
  list: (ownerId?: string) =>
    request<{ ledgers: LedgerSummary[] }>(
      `/list${ownerId ? `?owner_id=${encodeURIComponent(ownerId)}` : ""}`,
    ).then((payload) => payload.ledgers),

  create: (body: {
    name: string;
    base_currency?: string;
    fiscal_year_start_month?: number;
    chart_template?: string;
  }) =>
    request<Record<string, unknown>>("/create", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  get: (id: string) => request<LedgerSummary>(`/${encodeURIComponent(id)}`),

  accounts: (id: string) =>
    request<{ accounts: Array<{ code: string; name: string; type: string }> }>(
      `/${encodeURIComponent(id)}/accounts`,
    ).then((payload) => payload.accounts),

  entries: (id: string, options: { start?: string; end?: string; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (options.start) params.set("start", options.start);
    if (options.end) params.set("end", options.end);
    params.set("limit", String(options.limit ?? 100));
    return request<{ entries: JournalEntrySummary[] }>(
      `/${encodeURIComponent(id)}/entries?${params.toString()}`,
    ).then((payload) => payload.entries);
  },

  trialBalance: (id: string, asOf = today(), start?: string) => {
    const params = new URLSearchParams({ as_of: asOf });
    if (start) params.set("start", start);
    return request<TrialBalance>(`/${encodeURIComponent(id)}/trial-balance?${params.toString()}`);
  },

  balanceSheet: (id: string, asOf = today()) =>
    request<BalanceSheet>(
      `/${encodeURIComponent(id)}/balance-sheet?as_of=${encodeURIComponent(asOf)}`,
    ),

  incomeStatement: (id: string, start?: string, end = today()) => {
    const params = new URLSearchParams({ end });
    if (start) params.set("start", start);
    return request<IncomeStatement>(
      `/${encodeURIComponent(id)}/income-statement?${params.toString()}`,
    );
  },

  closePreview: (id: string, periodId?: string) =>
    request<CloseReport>(`/${encodeURIComponent(id)}/close/preview`, {
      method: "POST",
      body: JSON.stringify(periodId ? { period_id: periodId } : {}),
    }),

  closePeriod: (id: string, periodId: string) =>
    request<Record<string, unknown>>(
      `/${encodeURIComponent(id)}/periods/${encodeURIComponent(periodId)}/close`,
      { method: "POST", body: "{}" },
    ),

  aging: (id: string, kind: "AR" | "AP" = "AR", asOf = today()) =>
    request<AgingReport>(
      `/${encodeURIComponent(id)}/aging?kind=${kind}&as_of=${encodeURIComponent(asOf)}`,
    ),

  accountsDetailed: (id: string) =>
    request<{ accounts: LedgerAccount[] }>(`/${encodeURIComponent(id)}/accounts`).then(
      (payload) => payload.accounts,
    ),

  parties: (id: string, kind?: "CUSTOMER" | "VENDOR") =>
    request<{ parties: Party[] }>(
      `/${encodeURIComponent(id)}/parties${kind ? `?kind=${kind}` : ""}`,
    ).then((payload) => payload.parties),

  createParty: (id: string, body: { name: string; kind: "CUSTOMER" | "VENDOR" }) =>
    request<Party>(`/${encodeURIComponent(id)}/parties`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  taxCodes: (id: string) =>
    request<{ taxCodes: Array<{ code: string; name: string; rate: string }> }>(
      `/${encodeURIComponent(id)}/tax-codes`,
    ).then((payload) => payload.taxCodes),

  documents: (id: string, kind?: "INVOICE" | "BILL") =>
    request<{ documents: LedgerDocument[] }>(
      `/${encodeURIComponent(id)}/documents${kind ? `?kind=${kind}` : ""}`,
    ).then((payload) => payload.documents),

  createDocument: (
    id: string,
    body: {
      kind: "INVOICE" | "BILL";
      party_id: string;
      issue_date: string;
      lines: Array<{ account_code: string; unit_price: string; tax_code?: string; description?: string }>;
    },
  ) =>
    request<LedgerDocument>(`/${encodeURIComponent(id)}/documents`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  payDocument: (
    id: string,
    documentId: string,
    body: { date: string; amount: string; bank_account: string; reference?: string },
  ) =>
    request<Record<string, unknown>>(
      `/${encodeURIComponent(id)}/documents/${encodeURIComponent(documentId)}/pay`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  groups: () =>
    request<{ groups: LedgerGroup[] }>("/groups").then((payload) => payload.groups),

  createGroup: (body: { name: string; base_currency: string }) =>
    request<LedgerGroup>("/groups", { method: "POST", body: JSON.stringify(body) }),

  addGroupMember: (groupId: string, body: { ledger_id: string; ownership_pct?: string }) =>
    request<Record<string, unknown>>(
      `/groups/${encodeURIComponent(groupId)}/members`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  consolidate: (groupId: string, body: { as_of?: string; rates?: Record<string, string> }) =>
    request<ConsolidationReport>(
      `/groups/${encodeURIComponent(groupId)}/consolidate`,
      { method: "POST", body: JSON.stringify(body) },
    ),
};
