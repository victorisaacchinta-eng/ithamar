// Parity check: the browser engine (TypeScript, pdf.js) must agree with the
// Python engine (pdfplumber) on every sample statement, row for row.
//   npx tsx scripts/parity.ts <dir with *.pdf and *.audit.json>
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import { auditWords } from "../src/engine/audit";
import { wordsFromPages } from "../src/engine/pdf";

const dir = process.argv[2];
let failures = 0;
for (const f of readdirSync(dir).filter((x) => x.endsWith(".pdf")).sort()) {
  const py = JSON.parse(readFileSync(join(dir, f.replace(/\.pdf$/, ".audit.json")), "utf8"));
  const doc = await pdfjs.getDocument({ data: new Uint8Array(readFileSync(join(dir, f))), useSystemFonts: false, verbosity: 0 }).promise;
  const pages = [];
  for (let i = 1; i <= doc.numPages; i++) pages.push(await doc.getPage(i));
  const ts = auditWords(await wordsFromPages(pages), f);
  const problems: string[] = [];
  if (ts.rows.length !== py.rows.length) problems.push(`rows ${ts.rows.length} vs ${py.rows.length}`);
  if (ts.opening_balance !== py.opening_balance) problems.push(`opening ${ts.opening_balance} vs ${py.opening_balance}`);
  if (ts.closing_balance !== py.closing_balance) problems.push(`closing ${ts.closing_balance} vs ${py.closing_balance}`);
  for (let i = 0; i < Math.min(ts.rows.length, py.rows.length); i++) {
    const a = ts.rows[i], b = py.rows[i];
    for (const k of ["date", "debit", "credit", "balance", "status"] as const) {
      if (a[k] !== b[k]) problems.push(`row ${i} ${k}: ${a[k]} vs ${b[k]}`);
    }
    if (a.narration.replace(/\s/g, "") !== b.narration.replace(/\s/g, "")) problems.push(`row ${i} narration: ${a.narration} | ${b.narration}`);
    for (const k of ["rail", "counterparty", "vpa", "rrn", "utr"] as const) {
      if (a.decoded[k] !== b.decoded[k]) problems.push(`row ${i} ${k}: ${a.decoded[k]} vs ${b.decoded[k]}`);
    }
  }
  const kinds = (x: { kind: string; row: number }[]) => x.map((e) => `${e.kind}@${e.row}`).join(",");
  if (kinds(ts.repairs) !== kinds(py.repairs)) problems.push(`repairs ${kinds(ts.repairs)} vs ${kinds(py.repairs)}`);
  const unres = (x: { row: number; reason: string }[]) => x.map((u) => `${u.reason}@${u.row}`).join(",");
  if (unres(ts.unresolved) !== unres(py.unresolved)) problems.push(`unresolved ${unres(ts.unresolved)} vs ${unres(py.unresolved)}`);
  console.log(`${problems.length ? "FAIL" : "ok  "} ${f}  rows=${ts.rows.length} verified=${ts.summary.verified} repaired=${ts.summary.repaired} broken=${ts.summary.broken}`);
  problems.slice(0, 6).forEach((p) => console.log("     " + p));
  failures += problems.length ? 1 : 0;
}
process.exit(failures ? 1 : 0);
