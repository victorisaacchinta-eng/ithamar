"""ithamar command line.

  ithamar audit statement.pdf [--password P] [--json out.json] [--csv out.csv] [--no-fix]
  ithamar demo [--out DIR]
  ithamar bench DIR [--generate N]

`audit` exits 0 when every row is proven, 1 when the engine repaired rows
(proven, but after a correction), 2 when the statement needs a person.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ithamar import __version__
from ithamar.money import fmt_inr

_MARK = {"verified": "✓", "repaired": "↻", "broken": "✗", "unchecked": "·"}


def _print_audit(payload: dict, out=sys.stdout) -> None:
    s = payload["summary"]
    w = out.write
    w(f"\n  ITHAMAR {payload['version']}  {payload['source']}\n")
    if payload["bank"]:
        w(f"  {payload['bank']}\n")
    w(f"  opening {fmt_inr(payload['opening_balance']) or 'not printed'}   "
      f"closing {fmt_inr(payload['closing_balance']) or 'not printed'}\n\n")
    for r in payload["rows"]:
        dr = fmt_inr(r["debit"]) if r["debit"] else ""
        cr = fmt_inr(r["credit"]) if r["credit"] else ""
        w(f"  {_MARK.get(r['status'], '?')} {r['index'] + 1:>3}  {r['date'] or '':10}  "
          f"{(r['narration'] or '')[:38]:38}  {dr:>12}  {cr:>12}  {fmt_inr(r['balance']):>14}\n")
    w("\n")
    for e in payload["repairs"]:
        w(f"  ↻ row {e['row'] + 1}: {e['kind'].replace('_', ' ')}. {e['detail']}\n")
        for alt in e["rejected"]:
            w(f"      considered and rejected: {alt['detail']}\n")
    for u in payload["unresolved"]:
        w(f"  ✗ row {u['row'] + 1}: {u['reason'].replace('_', ' ')}\n")
        for c in u["candidates"]:
            w(f"      {c['detail']}\n")
    verdict = "PROVEN" if s["clean"] and not s["repaired"] else "PROVEN AFTER REPAIR" if s["clean"] else "NEEDS REVIEW"
    w(f"\n  {s['verified']}/{s['rows']} proven as printed, {s['repaired']} repaired, {s['broken']} broken, "
      f"{s['unchecked']} unchecked. Closing balance {'matches' if s['closing_ok'] else 'not confirmed' if s['closing_ok'] is None else 'DOES NOT MATCH'}.\n")
    w(f"  {verdict}\n\n")


def cmd_audit(a) -> int:
    from ithamar.parse import parse_pdf
    from ithamar.report import audit, write_csv, write_json

    st = parse_pdf(a.pdf, a.password)
    _, payload = audit(st, fix=not a.no_fix)
    if a.json:
        write_json(payload, a.json)
    if a.csv:
        write_csv(payload, a.csv)
    if not a.quiet:
        _print_audit(payload)
    s = payload["summary"]
    if s["clean"] and not s["repaired"]:
        return 0
    return 1 if s["clean"] else 2


def cmd_demo(a) -> int:
    from ithamar.bench.synthetic import generate
    from ithamar.parse import parse_pdf
    from ithamar.report import audit, write_json

    out = Path(a.out)
    for seed, layout, kinds in [(11, "ashoka", ["swap", "amount", "balance", "missing"]), (12, "konark", [])]:
        pdf, _ = generate(out, seed, layout, 30, kinds)
        _, payload = audit(parse_pdf(pdf))
        write_json(payload, pdf.with_suffix(".audit.json"))
        _print_audit(payload)
    print(f"  files in {out}/")
    return 0


def cmd_bench(a) -> int:
    from ithamar.bench.evaluate import bench, table
    from ithamar.bench.synthetic import generate

    folder = Path(a.folder)
    if a.generate:
        kinds_cycle = [[], ["swap"], ["amount"], ["balance"], ["missing"], ["swap", "balance"],
                       ["amount", "missing", "swap"], ["swap", "amount", "balance", "missing"]]
        for i in range(a.generate):
            generate(folder, i, None, 36, kinds_cycle[i % len(kinds_cycle)])
    scores = bench(folder)
    print(table(scores))
    return 0 if sum(s.false_verified for s in scores) == 0 else 3


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ithamar", description="Indian bank statements, extracted and proven row by row.")
    p.add_argument("--version", action="version", version=f"ithamar {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    au = sub.add_parser("audit", help="extract and prove one statement PDF")
    au.add_argument("pdf")
    au.add_argument("--password", default=None, help="PDF password (often DOB or part of the account number)")
    au.add_argument("--json")
    au.add_argument("--csv")
    au.add_argument("--no-fix", action="store_true", help="report rows exactly as printed; do not apply repairs")
    au.add_argument("-q", "--quiet", action="store_true")
    au.set_defaults(fn=cmd_audit)

    de = sub.add_parser("demo", help="generate synthetic statements and audit them")
    de.add_argument("--out", default="ithamar_demo")
    de.set_defaults(fn=cmd_demo)

    be = sub.add_parser("bench", help="score the engine on statements with known truth")
    be.add_argument("folder")
    be.add_argument("--generate", type=int, default=0)
    be.set_defaults(fn=cmd_bench)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
