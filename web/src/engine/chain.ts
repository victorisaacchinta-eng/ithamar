// The balance chain. Port of ithamar/verify/chain.py: same rules, same output.
import { BROKEN, Statement, Status, Transaction, UNCHECKED, VERIFIED, net } from "./models";
import { fmtInr } from "./money";

export const SWAP = "direction_swapped";
export const AMOUNT = "amount_misread";
export const BALANCE = "balance_misread";
export const MISSING = "missing_row";
export type Kind = typeof SWAP | typeof AMOUNT | typeof BALANCE | typeof MISSING;

export interface Hypothesis {
  kind: Kind;
  row: number;
  fix: Record<string, number | null>;
  closes: boolean;
  detail: string;
}

export interface Break {
  row: number;
  prev_balance: number;
  expected: number;
  printed: number;
  gap: number;
  hypotheses: Hypothesis[];
}

export interface ChainReport {
  statuses: Status[];
  breaks: Break[];
  anchor: "opening" | "first_row" | "none";
  closing_ok: boolean | null;
}

export const hypKey = (h: Hypothesis) =>
  `${h.kind}|${h.row}|${Object.keys(h.fix).sort().map((k) => `${k}=${h.fix[k]}`).join(",")}`;

export const reportClean = (r: ChainReport) => r.breaks.length === 0 && r.closing_ok !== false;

function editLe1(a: string, b: string): boolean {
  if (a === b) return false;
  if (a.length === b.length) {
    const diff: number[] = [];
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) diff.push(i);
    if (diff.length === 1) return true;
    return diff.length === 2 && diff[1] === diff[0] + 1 && a[diff[0]] === b[diff[1]] && a[diff[1]] === b[diff[0]];
  }
  if (Math.abs(a.length - b.length) !== 1) return false;
  const [s, l] = a.length < b.length ? [a, b] : [b, a];
  for (let i = 0; i < l.length; i++) if (l.slice(0, i) + l.slice(i + 1) === s) return true;
  return false;
}

export function digitsSimilar(a: number, b: number): boolean {
  a = Math.abs(a);
  b = Math.abs(b);
  if (a === b || a === 0 || b === 0) return false;
  if (editLe1(String(a), String(b))) return true;
  const hi = Math.max(a, b), lo = Math.min(a, b);
  return hi === lo * 10 || hi === lo * 100;
}

function nextChecked(txns: Transaction[], start: number): [number | null, number] {
  let carried = 0;
  for (let j = start; j < txns.length; j++) {
    if (txns[j].balance !== null) return [j, carried];
    carried += net(txns[j]);
  }
  return [null, carried];
}

function windowCloses(st: Statement, i: number, balanceI: number): boolean {
  const txns = st.transactions;
  const [j, carried] = nextChecked(txns, i + 1);
  if (j === null) {
    if (st.closing_balance === null) return false;
    return balanceI + carried === st.closing_balance;
  }
  return balanceI + carried + net(txns[j]) === txns[j].balance;
}

function hypotheses(st: Statement, i: number, prev: number, prevRow: number | null, prevComputed: number | null): Hypothesis[] {
  const t = st.transactions[i];
  const printed = t.balance as number;
  const n = net(t);
  const out: Hypothesis[] = [];
  const need = printed - prev;
  const downstreamOk = windowCloses(st, i, printed);
  const oneSided = (t.debit ?? 0) === 0 || (t.credit ?? 0) === 0;

  if (oneSided && n !== 0 && -n === need) {
    out.push({
      kind: SWAP, row: i, fix: { debit: t.credit, credit: t.debit }, closes: downstreamOk,
      detail: `${fmtInr(Math.abs(n))} is a ${n < 0 ? "credit" : "debit"}, not a ${n < 0 ? "debit" : "credit"}`,
    });
  }
  if (oneSided && n !== 0 && need !== 0 && need > 0 === n > 0 && digitsSimilar(n, need)) {
    const side = n > 0 ? "credit" : "debit";
    out.push({
      kind: AMOUNT, row: i, fix: { [side]: Math.abs(need) }, closes: downstreamOk,
      detail: `${side} reads ${fmtInr(Math.abs(n))}; the balances need ${fmtInr(Math.abs(need))}`,
    });
  }
  const corrected = prev + n;
  if (windowCloses(st, i, corrected)) {
    out.push({
      kind: BALANCE, row: i, fix: { balance: corrected }, closes: true,
      detail: `balance reads ${fmtInr(printed)}; the chain gives ${fmtInr(corrected)}`,
    });
  }
  if (prevRow !== null && prevComputed !== null && prevComputed + n === printed) {
    out.push({
      kind: BALANCE, row: prevRow, fix: { balance: prevComputed }, closes: true,
      detail: `row above: balance should be ${fmtInr(prevComputed)}`,
    });
  }
  const gap = printed - (prev + n);
  if (gap !== 0) {
    out.push({
      kind: MISSING, row: i, fix: { insert_before: i, net: gap }, closes: downstreamOk,
      detail: `a ${gap > 0 ? "credit" : "debit"} of ${fmtInr(Math.abs(gap))} may be missing above this row`,
    });
  }
  return out;
}

export function verify(st: Statement): ChainReport {
  const txns = st.transactions;
  const statuses: Status[] = txns.map(() => UNCHECKED);
  const breaks: Break[] = [];
  const first = txns.findIndex((t) => t.balance !== null);
  let prev: number, anchor: ChainReport["anchor"], start: number;

  if (st.opening_balance !== null) {
    prev = st.opening_balance; anchor = "opening"; start = 0;
  } else if (first >= 0) {
    prev = txns[first].balance as number; anchor = "first_row"; start = first + 1;
    const note = "no opening balance printed; first row is the anchor and is not proven";
    if (!st.warnings.includes(note)) st.warnings.push(note);
  } else {
    txns.forEach((t) => (t.status = UNCHECKED));
    return { statuses, breaks: [], anchor: "none", closing_ok: null };
  }

  let pending: number[] = [];
  let prevRow: number | null = null;
  let prevComputed: number | null = null;
  for (let i = start; i < txns.length; i++) {
    const t = txns[i];
    if (t.balance === null) { pending.push(i); continue; }
    const carried = pending.reduce((s, k) => s + net(txns[k]), 0);
    const expected = prev + carried + net(t);
    if (expected === t.balance) {
      statuses[i] = VERIFIED;
      prevComputed = null;
    } else {
      statuses[i] = BROKEN;
      breaks.push({
        row: i, prev_balance: prev + carried, expected, printed: t.balance, gap: t.balance - expected,
        hypotheses: hypotheses(st, i, prev + carried, prevRow, prevComputed),
      });
      prevComputed = expected;
    }
    pending = [];
    prev = t.balance;
    prevRow = i;
  }
  let closing_ok: boolean | null = null;
  if (st.closing_balance !== null) {
    const carried = pending.reduce((s, k) => s + net(txns[k]), 0);
    closing_ok = prev + carried === st.closing_balance;
  }
  txns.forEach((t, k) => (t.status = statuses[k]));
  return { statuses, breaks, anchor, closing_ok };
}
