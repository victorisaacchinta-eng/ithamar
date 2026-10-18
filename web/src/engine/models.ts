export const VERIFIED = "verified";
export const REPAIRED = "repaired";
export const BROKEN = "broken";
export const UNCHECKED = "unchecked";
export type Status = typeof VERIFIED | typeof REPAIRED | typeof BROKEN | typeof UNCHECKED;

export interface Transaction {
  index: number;
  date: string | null;
  narration: string;
  debit: number | null;
  credit: number | null;
  balance: number | null;
  value_date: string | null;
  ref: string;
  page: number;
  status: Status;
}

export interface Statement {
  transactions: Transaction[];
  opening_balance: number | null;
  closing_balance: number | null;
  source: string;
  bank: string;
  warnings: string[];
}

export const net = (t: Transaction): number => (t.credit ?? 0) - (t.debit ?? 0);

export function copyStatement(s: Statement): Statement {
  return { ...s, transactions: s.transactions.map((t) => ({ ...t })), warnings: [...s.warnings] };
}
