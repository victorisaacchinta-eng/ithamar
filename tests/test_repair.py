"""The repair contract. See ithamar/verify/repair.py for the rules these pin."""

from helpers import ledger
from hypothesis import given, settings
from hypothesis import strategies as st

from ithamar.models import BROKEN, REPAIRED, VERIFIED
from ithamar.verify import repair, verify

nets = st.lists(st.integers(-2_00_000_00, 2_00_000_00).filter(lambda n: abs(n) >= 1_00), min_size=8, max_size=40)


def _base():
    return ledger([5_000_00, -1_234_50, -200_00, 12_000_00, -3_450_00, -99_00, 7_500_00, -2_000_00])


def test_swap_is_repaired_and_marked_repaired():
    s = _base()
    t = s.transactions[3]
    t.debit, t.credit = t.credit, t.debit
    res = repair(s)
    assert res.report.clean
    assert res.statement.transactions[3].status == REPAIRED
    assert res.log[0]["kind"] == "direction_swapped"
    assert res.log[0]["rejected"][0]["kind"] == "missing_row"  # the alternative is shown, not hidden


def test_amount_misread_is_repaired():
    s = _base()
    s.transactions[4].debit = 3_480_00  # 3,450.00 read as 3,480.00
    res = repair(s)
    assert res.report.clean
    assert res.statement.transactions[4].debit == 3_450_00


def test_balance_misread_fixes_the_right_row():
    s = _base()
    true = s.transactions[2].balance
    s.transactions[2].balance = true + 9_00_00  # one digit
    rep = verify(s)
    assert [b.row for b in rep.breaks] == [2, 3]  # one bad cell, two breaks
    res = repair(s)
    assert res.report.clean
    assert res.statement.transactions[2].balance == true
    assert res.statement.transactions[2].status == REPAIRED
    assert res.statement.transactions[3].status == VERIFIED


def test_missing_row_is_never_invented():
    s = _base()
    del s.transactions[4]
    res = repair(s)
    assert not res.report.clean
    assert len(res.statement.transactions) == len(s.transactions)
    assert res.unresolved_detail[0].reason == "missing_row_suspected"
    assert res.unresolved_detail[0].candidates[0]["fix"]["net"] == -3_450_00


def test_input_is_never_mutated():
    s = _base()
    s.transactions[1].debit = 1_284_50
    before = [t.to_dict() for t in s.transactions]
    repair(s)
    assert [t.to_dict() for t in s.transactions] == before


def test_repair_never_invents_a_clean_chain_from_garbage():
    s = _base()
    for t in s.transactions[1:4]:
        t.balance += 12_345
    res = repair(s)
    assert res.unresolved or verify(res.statement).clean


def test_last_row_without_closing_balance_is_unconfirmable():
    s = _base()
    s.closing_balance = None
    last = s.transactions[-1]
    last.debit, last.credit = last.credit, last.debit  # wrong direction, and nothing below to confirm it
    res = repair(s)
    assert res.statement.transactions[-1].status == BROKEN
    assert res.unresolved_detail[0].reason in ("unconfirmable", "missing_row_suspected")


@settings(max_examples=200)
@given(nets, st.data())
def test_repair_never_marks_a_wrong_row_as_proven(ns, data):
    """The headline guarantee: whatever is injected, a row is only ever verified
    or repaired if its values equal the truth."""
    truth = ledger(ns)
    s = ledger(ns)
    k = data.draw(st.integers(1, len(ns) - 2))
    kind = data.draw(st.sampled_from(["swap", "amount", "balance"]))
    t = s.transactions[k]
    if kind == "swap":
        t.debit, t.credit = t.credit, t.debit
    elif kind == "amount":
        bump = data.draw(st.sampled_from([1, 9, 10, 90, 100, 900, 1000]))
        if t.debit:
            t.debit += bump
        else:
            t.credit += bump
    else:
        t.balance += data.draw(st.sampled_from([1, 10, 100, 1000, 10000]))
    res = repair(s)
    for got, want in zip(res.statement.transactions, truth.transactions):
        if got.status in (VERIFIED, REPAIRED):
            assert (got.debit or 0, got.credit or 0, got.balance) == (want.debit or 0, want.credit or 0, want.balance)
