"""The audit payload writers and the --no-fix path, without rendering a PDF."""

import csv
import json

from helpers import ledger

from ithamar.models import BROKEN, REPAIRED
from ithamar.report import audit, write_csv, write_json


def _swapped():
    s = ledger([5_000_00, -1_234_50, -200_00, 12_000_00, -3_450_00])
    s.transactions[0].narration = "UPI/412345678901/RENT/ravi.kumar@okaxis/RAVI KUMAR"
    t = s.transactions[3]
    t.debit, t.credit = t.credit, t.debit
    return s


def test_no_fix_reports_rows_as_printed():
    s = _swapped()
    _, p = audit(s, fix=False)
    assert p["rows"][3]["debit"] == 12_000_00 and p["rows"][3]["status"] == BROKEN
    assert p["repairs"] == [] and p["unresolved"] == []
    assert not p["summary"]["clean"]
    assert s.transactions[3].debit == 12_000_00  # the caller's statement is not mutated


def test_fix_repairs_the_same_row():
    _, p = audit(_swapped())
    assert p["rows"][3]["credit"] == 12_000_00 and p["rows"][3]["status"] == REPAIRED
    assert p["summary"]["clean"]


def test_csv_has_rupees_blanks_and_decoded_columns(tmp_path):
    _, p = audit(_swapped())
    out = tmp_path / "out.csv"
    write_csv(p, out)
    with out.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 5
    first = rows[0]
    assert first["credit"] == "5000.00" and first["debit"] == ""
    assert first["balance"] == "15000.00"
    assert (first["rail"], first["vpa"], first["rrn"]) == ("UPI", "ravi.kumar@okaxis", "412345678901")
    assert rows[1]["debit"] == "1234.50"


def test_json_round_trips_and_keeps_paise(tmp_path):
    _, p = audit(_swapped())
    p["bank"] = "Ashoka Bank ₹"
    out = tmp_path / "out.json"
    write_json(p, out)
    assert "₹" in out.read_text(encoding="utf-8")  # ensure_ascii=False
    back = json.loads(out.read_text(encoding="utf-8"))
    assert back == p
    assert back["rows"][1]["debit"] == 1_234_50


def test_csv_quotes_formula_text_but_not_money(tmp_path):
    s = ledger([5_000_00, -1_234_50, -200_00], opening=-10_000_00)  # overdrawn, so balances are negative
    s.transactions[0].narration = '=HYPERLINK("http://x.example","Refund")'
    s.transactions[1].narration = "@SUM(A1:A9)"
    s.transactions[1].ref = "+91000"
    s.transactions[2].narration = "-cmd|' /C calc'!A0"
    _, p = audit(s)
    p["rows"][2]["decoded"]["counterparty"] = "\tTAB LTD"
    out = tmp_path / "out.csv"
    write_csv(p, out)
    with out.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["narration"] == "'" + '=HYPERLINK("http://x.example","Refund")'
    assert rows[1]["narration"] == "'@SUM(A1:A9)" and rows[1]["ref"] == "'+91000"
    assert rows[2]["narration"].startswith("'-cmd")
    assert rows[2]["counterparty"] == "'\tTAB LTD"
    assert rows[0]["balance"] == "-5000.00"  # money stays numeric
    assert rows[1]["debit"] == "1234.50" and rows[2]["balance"] == "-6434.50"
    assert p["rows"][0]["narration"].startswith("=")  # the JSON payload is unchanged


def test_csv_leaves_ordinary_text_alone(tmp_path):
    _, p = audit(_swapped())
    out = tmp_path / "out.csv"
    write_csv(p, out)
    with out.open(newline="", encoding="utf-8") as f:
        first = next(csv.DictReader(f))
    assert first["narration"] == "UPI/412345678901/RENT/ravi.kumar@okaxis/RAVI KUMAR"
    assert first["vpa"] == "ravi.kumar@okaxis"
