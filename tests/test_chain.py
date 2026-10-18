"""Property tests: the chain must catch every single corruption, on any ledger."""

from helpers import ledger
from hypothesis import given, settings
from hypothesis import strategies as st

from ithamar.models import BROKEN, UNCHECKED, VERIFIED
from ithamar.verify import digits_similar, verify

nets = st.lists(st.integers(-5_00_000_00, 5_00_000_00).filter(lambda n: n != 0), min_size=3, max_size=60)


@given(nets)
def test_clean_ledger_always_verifies(ns):
    rep = verify(ledger(ns))
    assert rep.clean and rep.verified == len(ns)


@settings(max_examples=300)
@given(nets, st.data())
def test_any_swap_is_caught(ns, data):
    s = ledger(ns)
    i = data.draw(st.integers(0, len(ns) - 1))
    t = s.transactions[i]
    t.debit, t.credit = t.credit, t.debit
    rep = verify(s)
    assert s.transactions[i].status == BROKEN
    assert not rep.clean


@settings(max_examples=300)
@given(nets, st.data())
def test_any_amount_change_is_caught(ns, data):
    s = ledger(ns)
    i = data.draw(st.integers(0, len(ns) - 1))
    delta = data.draw(st.integers(1, 10_00_000).map(lambda d: d * data.draw(st.sampled_from([1, -1]))))
    t = s.transactions[i]
    if t.debit:
        if t.debit + delta <= 0:
            delta = 1
        t.debit += delta
    else:
        if t.credit + delta <= 0:
            delta = 1
        t.credit += delta
    verify(s)
    assert s.transactions[i].status == BROKEN


@settings(max_examples=300)
@given(nets, st.data())
def test_any_balance_change_is_caught(ns, data):
    s = ledger(ns)
    i = data.draw(st.integers(0, len(ns) - 1))
    s.transactions[i].balance += data.draw(st.integers(1, 10_00_000))
    rep = verify(s)
    assert s.transactions[i].status == BROKEN
    assert not rep.clean  # either the next row or the closing balance disagrees too


@settings(max_examples=300)
@given(nets, st.data())
def test_any_deleted_row_is_caught(ns, data):
    s = ledger(ns)
    i = data.draw(st.integers(0, len(ns) - 1))
    del s.transactions[i]
    rep = verify(s)
    assert not rep.clean


def test_resync_keeps_one_break_local():
    s = ledger([100_00, -50_00, 200_00, -30_00, 10_00])
    s.transactions[2].credit = 201_00  # one bad amount
    rep = verify(s)
    assert [b.row for b in rep.breaks] == [2]
    assert [t.status for t in s.transactions] == [VERIFIED, VERIFIED, BROKEN, VERIFIED, VERIFIED]


def test_rows_without_balance_are_unchecked_but_summed():
    s = ledger([100_00, -50_00, 200_00])
    s.transactions[1].balance = None
    rep = verify(s)
    assert rep.clean
    assert s.transactions[1].status == UNCHECKED
    assert s.transactions[2].status == VERIFIED


def test_no_opening_balance_anchors_on_first_row():
    s = ledger([100_00, -50_00, 200_00])
    s.opening_balance = None
    rep = verify(s)
    assert rep.anchor == "first_row"
    assert s.transactions[0].status == UNCHECKED
    assert rep.verified == 2


def test_closing_mismatch_is_reported():
    s = ledger([100_00, -50_00])
    s.closing_balance += 1
    rep = verify(s)
    assert rep.closing_ok is False and not rep.clean


def test_digits_similar():
    assert digits_similar(123456, 123856)      # one digit
    assert digits_similar(123456, 124356)      # adjacent swap
    assert digits_similar(123456, 12346)       # dropped digit
    assert digits_similar(5000, 50000)         # decimal shift
    assert not digits_similar(123456, 654321)
    assert not digits_similar(100, 100)
