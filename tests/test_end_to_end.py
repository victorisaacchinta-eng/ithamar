"""Render real PDFs, parse them back, and demand exact results."""

import pytest

from ithamar.bench.evaluate import score
from ithamar.bench.synthetic import LAYOUTS, generate
from ithamar.parse import parse_pdf
from ithamar.report import audit


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_clean_statement_round_trips_exactly(tmp_path, layout):
    pdf, truth = generate(tmp_path, 3, layout, 50, [])
    st = parse_pdf(pdf)
    assert st.opening_balance == truth.opening_balance
    assert st.closing_balance == truth.closing_balance
    assert len(st.transactions) == len(truth.printed)
    for got, want in zip(st.transactions, truth.printed):
        assert (got.date, got.debit, got.credit, got.balance) == (want.date, want.debit, want.credit, want.balance)
        assert got.narration.replace(" ", "") == want.narration.replace(" ", "")
    _, payload = audit(st)
    assert payload["summary"]["clean"] and payload["summary"]["verified"] == len(truth.printed)


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_every_injected_error_is_caught_and_none_is_proven(tmp_path, layout):
    pdf, _ = generate(tmp_path, 9, layout, 40, ["swap", "amount", "balance", "missing"])
    s = score(pdf)
    assert s.caught == s.injected == 4
    assert s.false_verified == 0
    assert s.repaired == s.repaired_correct == 3  # swap, amount, balance fixed; missing left for a person


def test_audit_payload_shape(tmp_path):
    pdf, _ = generate(tmp_path, 4, "konark", 20, ["swap"])
    _, p = audit(parse_pdf(pdf))
    assert p["tool"] == "ithamar"
    assert p["summary"]["repaired"] == 1
    assert p["repairs"][0]["kind"] == "direction_swapped"
    assert {"rail", "vpa", "rrn"} <= set(p["rows"][0]["decoded"])
