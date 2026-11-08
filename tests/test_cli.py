"""`ithamar audit` must exit 2 with a clear message when the PDF cannot be opened.

A traceback exits 1, which the documented exit codes reserve for
"proven after repair", so a gating script would wrongly pass.
"""

from __future__ import annotations

import pytest

from ithamar.cli import main


@pytest.fixture
def locked_pdf(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "locked.pdf"
    c = canvas.Canvas(str(path), encrypt="secret")
    c.drawString(100, 700, "statement")
    c.save()
    return path


def test_missing_file(tmp_path, capsys):
    assert main(["audit", str(tmp_path / "nope.pdf"), "-q"]) == 2
    assert "cannot open" in capsys.readouterr().err


def test_not_a_pdf(tmp_path, capsys):
    path = tmp_path / "junk.pdf"
    path.write_text("not a pdf")
    assert main(["audit", str(path), "-q"]) == 2
    assert "not a readable PDF" in capsys.readouterr().err


def test_password_missing(locked_pdf, capsys):
    assert main(["audit", str(locked_pdf), "-q"]) == 2
    assert "pass --password" in capsys.readouterr().err


def test_password_wrong(locked_pdf, capsys):
    assert main(["audit", str(locked_pdf), "--password", "nope", "-q"]) == 2
    assert "wrong password" in capsys.readouterr().err
