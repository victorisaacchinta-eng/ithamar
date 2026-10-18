// Positioned words in, a Statement out. Port of ithamar/parse/layout.py.
// No bank templates: columns are learned from the header row on each page.
import { parseDate } from "./dates";
import { Statement, Transaction, UNCHECKED } from "./models";
import { looksLikeAmount, parseAmount } from "./money";

export interface Word { text: string; x0: number; x1: number; top: number; page: number }
interface Column { field: string; x0: number; x1: number }

const FIELDS: [string, string[]][] = [
  ["value_date", ["value date", "value dt", "val dt"]],
  ["dir", ["dr cr", "cr dr", "dr/cr", "type"]],
  ["ref", ["chq", "cheque", "ref", "reference", "instrument"]],
  ["debit", ["withdrawal", "debit", "paid out", "dr amount"]],
  ["credit", ["deposit", "credit", "paid in", "cr amount"]],
  ["balance", ["balance"]],
  ["amount", ["amount"]],
  ["date", ["date", "txn dt", "tran dt", "txn date"]],
  ["narration", ["narration", "description", "particulars", "remarks", "details", "transaction"]],
];
const NUMERIC = new Set(["debit", "credit", "amount", "balance"]);
const STOP = /page \d+ of \d+|end of statement|statement summary|this is a (computer|system)|\*\*\* end/i;
const YEAR = /\b(20\d{2})\b/;
const OPENING = /opening\s+balance|balance\s+b\/?f|brought\s+forward/i;
const CLOSING = /closing\s+balance|balance\s+c\/?f|carried\s+forward/i;
const SUMMARY_AMT = /(\(?-?(?:INR|Rs\.?|₹)?\s*\d{1,3}(?:,\d{2,3})*\.\d{2}\)?(?:\s*(?:Cr|Dr|CR|DR))?)/g;

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export function classify(header: string): string | null {
  const h = ` ${norm(header)} `;
  for (const [field, keys] of FIELDS) for (const k of keys) if (h.includes(` ${norm(k)} `)) return field;
  return null;
}

export function linesOf(words: Word[], tol = 3.0): Word[][] {
  const sorted = [...words].sort((a, b) => a.page - b.page || Math.round(a.top * 10) - Math.round(b.top * 10) || a.x0 - b.x0);
  const out: Word[][] = [];
  for (const w of sorted) {
    const last = out[out.length - 1];
    if (last && last[0].page === w.page && Math.abs(last[0].top - w.top) <= tol) last.push(w);
    else out.push([w]);
  }
  out.forEach((l) => l.sort((a, b) => a.x0 - b.x0));
  return out;
}

function mergeSuffixes(line: Word[]): Word[] {
  const merged: Word[] = [];
  for (const w of line) {
    const t = w.text.replace(/^\.+|\.+$/g, "");
    const p = merged[merged.length - 1];
    if (p && (t.toLowerCase() === "dr" || t.toLowerCase() === "cr") && looksLikeAmount(p.text) && w.x0 - p.x1 < 8) {
      merged[merged.length - 1] = { text: `${p.text} ${t}`, x0: p.x0, x1: w.x1, top: p.top, page: p.page };
    } else merged.push(w);
  }
  return merged;
}

function headerColumns(line: Word[], gap = 7.0): Column[] | null {
  const cells: Word[][] = [];
  for (const w of line) {
    const c = cells[cells.length - 1];
    if (c && w.x0 - c[c.length - 1].x1 < gap) c.push(w);
    else cells.push([w]);
  }
  const cols: Column[] = [];
  for (const c of cells) {
    const field = classify(c.map((w) => w.text).join(" "));
    if (field) cols.push({ field, x0: c[0].x0, x1: c[c.length - 1].x1 });
  }
  const names = new Set(cols.map((c) => c.field));
  const hasMoney = names.has("debit") || names.has("credit") || names.has("amount");
  if (!(names.has("balance") && names.has("date") && hasMoney)) return null;
  const seen = new Set<string>();
  const out: Column[] = [];
  for (let c of cols) {
    if (c.field === "date" && seen.has("date")) c = { ...c, field: "value_date" };
    if (!seen.has(c.field)) { seen.add(c.field); out.push(c); }
  }
  return out;
}

function assign(line: Word[], cols: Column[]): Record<string, Word[]> {
  const cells: Record<string, Word[]> = {};
  cols.forEach((c) => (cells[c.field] = []));
  const numeric = cols.filter((c) => NUMERIC.has(c.field));
  const ordered = [...cols].sort((a, b) => a.x0 - b.x0);
  for (const w of line) {
    if (numeric.length && looksLikeAmount(w.text)) {
      const best = numeric.reduce((a, b) => (Math.abs(b.x1 - w.x1) < Math.abs(a.x1 - w.x1) ? b : a));
      if (Math.abs(best.x1 - w.x1) <= 40 || (best.x0 - 4 <= w.x0 && w.x0 <= best.x1 + 4)) {
        cells[best.field].push(w);
        continue;
      }
    }
    let owner: Column | null = null;
    for (const c of ordered) if (c.x0 <= w.x0 + 3) owner = c;
    if (!owner) owner = ordered[0];
    if (NUMERIC.has(owner.field)) {
      const textCols = ordered.filter((c) => !NUMERIC.has(c.field) && c.x0 <= w.x0 + 3);
      owner = textCols.length ? textCols[textCols.length - 1] : ordered[0];
    }
    cells[owner.field].push(w);
  }
  return cells;
}

const text = (ws: Word[] | undefined) => (ws ?? []).map((w) => w.text).join(" ").trim();

function money(ws: Word[] | undefined) {
  for (const w of ws ?? []) {
    const m = parseAmount(w.text);
    if (m) return m;
  }
  return null;
}

function summaryAmount(lineText: string): number | null {
  const m = lineText.match(SUMMARY_AMT);
  if (!m) return null;
  const p = parseAmount(m[m.length - 1]);
  if (!p) return null;
  return p[1] === "Dr" ? -Math.abs(p[0]) : p[0];
}

export function joinWrapped(head: string, tail: string): string {
  if (!head) return tail;
  if (/[/-]$/.test(head) || /^[/-]/.test(tail)) return head + tail;
  return `${head} ${tail}`;
}

const signed = (m: [number, string | null] | null) => (m ? (m[1] === "Dr" ? -Math.abs(m[0]) : m[0]) : null);

export function parseWords(words: Word[], source = ""): Statement {
  const all = words.map((w) => w.text).join(" ");
  const ym = YEAR.exec(all);
  const defaultYear = ym ? parseInt(ym[1], 10) : null;
  const st: Statement = { transactions: [], opening_balance: null, closing_balance: null, source, bank: "", warnings: [] };
  let cols: Column[] | null = null;
  let current: Transaction | null = null;
  let lastTop: number | null = null;
  let lastPage = -1;
  let inTable = false;
  const lineH = 12.0;

  for (const raw of linesOf(words)) {
    const line = mergeSuffixes(raw);
    const t = text(line);
    const page = line[0].page;
    if (page !== lastPage) {
      inTable = cols !== null;
      lastTop = null;
      lastPage = page;
      if (!st.bank && page === 0 && t) st.bank = t;
    }
    const hdr = headerColumns(line);
    if (hdr) { cols = hdr; inTable = true; current = null; lastTop = line[0].top; continue; }

    if (cols === null) {
      if (OPENING.test(t) && st.opening_balance === null) st.opening_balance = summaryAmount(t);
      else if (CLOSING.test(t) && st.closing_balance === null) st.closing_balance = summaryAmount(t);
      continue;
    }
    if (STOP.test(t)) {
      inTable = false; current = null;
      if (CLOSING.test(t) && st.closing_balance === null) st.closing_balance = summaryAmount(t);
      continue;
    }
    if (!inTable) {
      if (CLOSING.test(t) && st.closing_balance === null) st.closing_balance = summaryAmount(t);
      else if (OPENING.test(t) && st.opening_balance === null) st.opening_balance = summaryAmount(t);
      continue;
    }

    const cells = assign(line, cols);
    const dateTxt = text(cells.date);
    const dt = dateTxt ? parseDate(dateTxt, defaultYear) : null;
    const narration = text(cells.narration);

    if (dt === null) {
      if (OPENING.test(t) && st.opening_balance === null) {
        const bal = money(cells.balance);
        if (bal) st.opening_balance = signed(bal);
        continue;
      }
      if (CLOSING.test(t)) {
        if (st.closing_balance === null) st.closing_balance = summaryAmount(t);
        inTable = false;
        continue;
      }
      const near = lastTop !== null && line[0].top - lastTop <= 2.4 * lineH;
      const hasNumbers = [...NUMERIC].some((f) => (cells[f] ?? []).length > 0);
      if (current && near && !hasNumbers) {
        current.narration = joinWrapped(current.narration, narration || t);
        const refExtra = text(cells.ref);
        if (refExtra && narration) current.ref = `${current.ref}${refExtra}`;
        lastTop = line[0].top;
      }
      continue;
    }

    if (OPENING.test(narration) && !(cells.debit ?? []).length && !(cells.credit ?? []).length && !(cells.amount ?? []).length) {
      const bal = money(cells.balance);
      if (bal && st.opening_balance === null) st.opening_balance = signed(bal);
      continue;
    }

    let debit: number | null = null;
    let credit: number | null = null;
    if ((cells.amount ?? []).length) {
      const amt = money(cells.amount);
      if (amt) {
        const dir = text(cells.dir).toLowerCase();
        const marker = amt[1] ?? (dir.startsWith("d") ? "Dr" : dir.startsWith("c") ? "Cr" : null);
        if (marker === "Dr" || amt[0] < 0) debit = Math.abs(amt[0]);
        else if (marker === "Cr") credit = Math.abs(amt[0]);
        else { st.warnings.push(`row ${st.transactions.length}: amount without direction`); credit = Math.abs(amt[0]); }
      }
    }
    if ((cells.debit ?? []).length) { const m = money(cells.debit); debit = m ? Math.abs(m[0]) : null; }
    if ((cells.credit ?? []).length) { const m = money(cells.credit); credit = m ? Math.abs(m[0]) : null; }
    const vd = text(cells.value_date);
    current = {
      index: st.transactions.length, date: dt, value_date: vd ? parseDate(vd, defaultYear) : null,
      narration, ref: text(cells.ref), debit, credit, balance: signed(money(cells.balance)), page, status: UNCHECKED,
    };
    st.transactions.push(current);
    lastTop = line[0].top;
  }
  if (cols === null) st.warnings.push("no transaction table header found");
  return st;
}
