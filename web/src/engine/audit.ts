// One entry point: words in, the same audit payload the Python CLI writes.
import { parseWords, Word } from "./layout";
import { decode, Decoded } from "./narration";
import { repair, RepairEntry, Unresolved } from "./repair";
import { Statement, Transaction } from "./models";
import { Break, reportClean } from "./chain";

export const VERSION = "0.2.0";

export interface AuditRow extends Transaction { decoded: Decoded }
export interface Audit {
  tool: "ithamar";
  version: string;
  source: string;
  bank: string;
  opening_balance: number | null;
  closing_balance: number | null;
  summary: {
    rows: number; verified: number; repaired: number; broken: number; unchecked: number;
    closing_ok: boolean | null; anchor: string; clean: boolean;
  };
  rows: AuditRow[];
  printed: Transaction[]; // the rows exactly as parsed, before any repair
  breaks: Break[];
  repairs: RepairEntry[];
  unresolved: Unresolved[];
  warnings: string[];
}

export function auditStatement(st: Statement): Audit {
  const printed = st.transactions.map((t) => ({ ...t }));
  const res = repair(st);
  const rows = res.statement.transactions.map((t) => ({ ...t, decoded: decode(t.narration) }));
  const count = (s: string) => rows.filter((r) => r.status === s).length;
  return {
    tool: "ithamar",
    version: VERSION,
    source: st.source.split("/").pop() ?? "",
    bank: st.bank,
    opening_balance: st.opening_balance,
    closing_balance: st.closing_balance,
    summary: {
      rows: rows.length, verified: count("verified"), repaired: count("repaired"), broken: count("broken"),
      unchecked: count("unchecked"), closing_ok: res.report.closing_ok, anchor: res.report.anchor, clean: reportClean(res.report),
    },
    rows,
    printed,
    breaks: res.report.breaks,
    repairs: res.log,
    unresolved: res.unresolved,
    warnings: res.statement.warnings,
  };
}

export const auditWords = (words: Word[], source = "") => auditStatement(parseWords(words, source));
