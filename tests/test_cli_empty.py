"""A statement with zero transactions must not be reported as PROVEN.

An empty chain has no breaks, so ChainReport.clean is true. `ithamar audit`
must still exit 2 (needs a person), since nothing was proven.
"""

from __future__ import annotations

import io

from ithamar import cli
from ithamar.models import Statement
from ithamar.report import audit


def test_print_audit_zero_rows_is_not_proven():
    _, payload = audit(Statement(transactions=[], source="empty.pdf"))
    assert payload["summary"]["rows"] == 0 and payload["summary"]["clean"]
    out = io.StringIO()
    cli._print_audit(payload, out)
    text = out.getvalue()
    assert "NEEDS REVIEW (no transactions found)" in text
    assert "  PROVEN\n" not in text


def test_audit_zero_rows_exits_2(monkeypatch, capsys):
    monkeypatch.setattr("ithamar.parse.parse_pdf",
                        lambda path, password=None: Statement(transactions=[], source=path))
    assert cli.main(["audit", "empty.pdf", "-q"]) == 2
    assert "no transactions found" in capsys.readouterr().err
