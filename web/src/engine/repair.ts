// Repair: choose between explanations, and refuse when the choice is not earned.
// Port of ithamar/verify/repair.py. The rules are documented there.
import { Break, ChainReport, Hypothesis, MISSING, hypKey, verify } from "./chain";
import { REPAIRED, Statement, VERIFIED, copyStatement } from "./models";

export interface Candidate { kind: string; row: number; fix: Record<string, number | null>; detail: string }
export interface Unresolved {
  row: number;
  reason: "ambiguous" | "no_explanation" | "missing_row_suspected" | "unconfirmable";
  candidates: Candidate[];
}
export interface RepairEntry {
  row: number;
  break_at: number;
  kind: string;
  before: Record<string, number | null>;
  after: Record<string, number | null>;
  detail: string;
  rejected: Candidate[];
}
export interface RepairResult { statement: Statement; report: ChainReport; log: RepairEntry[]; unresolved: Unresolved[] }

const MAX_ROUNDS = 50;
const describe = (h: Hypothesis): Candidate => ({ kind: h.kind, row: h.row, fix: { ...h.fix }, detail: h.detail });

export function decide(brk: Break): [Hypothesis | null, Unresolved | null, Hypothesis[]] {
  const seen = new Map<string, Hypothesis>();
  for (const h of brk.hypotheses) if (h.closes) seen.set(hypKey(h), h);
  const closing = [...seen.values()];
  const specific = closing.filter((h) => h.kind !== MISSING);
  const missing = closing.filter((h) => h.kind === MISSING);
  if (specific.length === 1) return [specific[0], null, missing];
  if (specific.length > 1) return [null, { row: brk.row, reason: "ambiguous", candidates: [...specific, ...missing].map(describe) }, []];
  if (missing.length) return [null, { row: brk.row, reason: "missing_row_suspected", candidates: missing.map(describe) }, []];
  if (brk.hypotheses.length) return [null, { row: brk.row, reason: "unconfirmable", candidates: brk.hypotheses.map(describe) }, []];
  return [null, { row: brk.row, reason: "no_explanation", candidates: [] }, []];
}

type Field = "debit" | "credit" | "balance";

export function repair(input: Statement): RepairResult {
  const st = copyStatement(input);
  let report = verify(st);
  const log: RepairEntry[] = [];
  const parked = new Map<number, Unresolved>();

  for (let round = 0; round < MAX_ROUNDS; round++) {
    let progressed = false;
    for (const brk of report.breaks) {
      if (parked.has(brk.row)) continue;
      const [accepted, unresolved, rejected] = decide(brk);
      if (!accepted) { parked.set(brk.row, unresolved!); continue; }
      const t = st.transactions[accepted.row];
      const before: Record<string, number | null> = {};
      for (const k of Object.keys(accepted.fix)) before[k] = t[k as Field];
      for (const [k, v] of Object.entries(accepted.fix)) t[k as Field] = v;
      const trial = verify(st);
      if (trial.breaks.length >= report.breaks.length) {
        for (const [k, v] of Object.entries(before)) t[k as Field] = v;
        parked.set(brk.row, { row: brk.row, reason: "no_explanation", candidates: [describe(accepted)] });
        report = verify(st);
        continue;
      }
      log.push({
        row: accepted.row, break_at: brk.row, kind: accepted.kind, before, after: { ...accepted.fix },
        detail: accepted.detail, rejected: rejected.map(describe),
      });
      report = trial;
      progressed = true;
      break;
    }
    if (!progressed) break;
  }

  report = verify(st);
  const live = new Set(report.breaks.map((b) => b.row));
  const unresolved = [...parked.entries()].sort((a, b) => a[0] - b[0]).filter(([r]) => live.has(r)).map(([, u]) => u);
  for (const b of report.breaks) if (!parked.has(b.row)) unresolved.push({ row: b.row, reason: "no_explanation", candidates: [] });
  const touched = new Set(log.map((e) => e.row));
  st.transactions.forEach((t, k) => {
    if (touched.has(k) && t.status === VERIFIED) { t.status = REPAIRED; report.statuses[k] = REPAIRED; }
  });
  return { statement: st, report, log, unresolved };
}
