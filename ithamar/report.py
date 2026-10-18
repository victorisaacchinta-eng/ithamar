"""Audit payload: one JSON shape shared by the CLI, the tests and the web page."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from ithamar import __version__
from ithamar.models import Statement
from ithamar.narration import decode
from ithamar.verify import RepairResult, repair


def audit(statement: Statement, fix: bool = True) -> tuple[RepairResult, dict]:
    """Verify, optionally repair, and build the payload.

    With fix=False the repair search still runs (so the payload can show what
    it would do) but the rows are reported exactly as printed.
    """
    result = repair(statement)
    st = result.statement if fix else statement
    if not fix:
        from ithamar.verify import verify
        report = verify(st)
    else:
        report = result.report

    rows = []
    for t in st.transactions:
        d = t.to_dict()
        d["decoded"] = decode(t.narration).to_dict()
        rows.append(d)

    summary = {
        "rows": len(rows),
        "verified": sum(r["status"] == "verified" for r in rows),
        "repaired": sum(r["status"] == "repaired" for r in rows),
        "broken": sum(r["status"] == "broken" for r in rows),
        "unchecked": sum(r["status"] == "unchecked" for r in rows),
        "closing_ok": report.closing_ok,
        "anchor": report.anchor,
        "clean": report.clean,
    }
    payload = {
        "tool": "ithamar",
        "version": __version__,
        "source": Path(statement.source).name if statement.source else "",
        "bank": statement.bank,
        "opening_balance": statement.opening_balance,
        "closing_balance": statement.closing_balance,
        "summary": summary,
        "rows": rows,
        "breaks": [
            {**{k: v for k, v in asdict(b).items() if k != "hypotheses"},
             "gap": b.gap, "hypotheses": [asdict(h) for h in b.hypotheses]}
            for b in report.breaks
        ],
        "repairs": result.log if fix else [],
        "unresolved": [asdict(u) for u in result.unresolved_detail] if fix else [],
        "warnings": st.warnings,
    }
    return result, payload


def write_json(payload: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, indent=1, ensure_ascii=False))


def write_csv(payload: dict, path: str | Path) -> None:
    fields = ["index", "date", "value_date", "narration", "ref", "debit", "credit", "balance",
              "status", "rail", "vpa", "rrn", "utr", "counterparty"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in payload["rows"]:
            row = {k: r.get(k, "") for k in fields}
            for k in ("rail", "vpa", "rrn", "utr", "counterparty"):
                row[k] = r["decoded"].get(k, "")
            for k in ("debit", "credit", "balance"):  # CSV gets rupees, JSON keeps paise
                if r[k] is not None:
                    row[k] = f"{r[k] / 100:.2f}"
            w.writerow(row)
