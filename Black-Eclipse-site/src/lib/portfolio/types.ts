// Shared portfolio data types — consumed by the pure cost engine
// (src/hooks/use-portfolio-engine.ts), the analysis library and the
// Portfolio screen. Kept dependency-free so both tests and app code
// can import it from anywhere.

export type TxType = 'BUY' | 'SELL' | 'DEPOSIT' | 'WITHDRAWAL' | 'DIVIDEND';

export interface Transaction {
  id: string;
  type: TxType;
  symbol: string;
  quantity: number;
  price: number;
  fee: number;
  date: string;
  notes?: string;
}

/** A guest/localStorage-backed fund: name, styling and its tx ledger. */
export interface Fund {
  id: string;
  name: string;
  icon: string;
  accent: string;
  /** Optional goal the user can set for progress display. */
  goalValue?: number | null;
  createdAt: string;
  /** Seeded demo funds are protected from deletion. */
  seeded?: boolean;
  transactions: Transaction[];
}

export const newTxId = () => `tx-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
