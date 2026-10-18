"""The balance chain: the one check a bank statement carries inside itself.

Every printed row obeys   previous balance + credit - debit = balance.
Walk that equation down the statement and each row is either proven by
arithmetic or it is not. Nothing here is a heuristic or a model guess.

When a row does not close, the chain resyncs on the printed balance, so one
bad cell produces one or two breaks instead of corrupting everything below it.
Each break is then tested against four concrete explanations, each with the
exact correction it implies. Choosing between them is repair's job, not this
module's.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ithamar.models import BROKEN, UNCHECKED, VERIFIED, Statement, Transaction
from ithamar.money import fmt_inr

# The four ways an extracted row usually goes wrong.
SWAP = "direction_swapped"      # the amount landed in the wrong column
AMOUNT = "amount_misread"       # a digit in the debit/credit cell was read wrong
BALANCE = "balance_misread"     # a digit in the balance cell was read wrong
MISSING = "missing_row"         # a whole transaction is absent between two rows


@dataclass
class Hypothesis:
    kind: str
    row: int                 # list position of the row the correction touches
    fix: dict                # field -> corrected value (paise), or {"insert_before", "net"}
    closes: bool             # applying it makes every row in the local window close
    detail: str = ""

    @property
    def key(self) -> tuple:
        return (self.kind, self.row, tuple(sorted(self.fix.items())))


@dataclass
class Break:
    row: int                 # list position of the row that fails
    prev_balance: int        # balance the chain carried into this row
    expected: int            # prev_balance + credit - debit
    printed: int             # the balance actually printed
    hypotheses: list[Hypothesis] = field(default_factory=list)

    @property
    def gap(self) -> int:
        return self.printed - self.expected


@dataclass
class ChainReport:
    statuses: list[str]
    breaks: list[Break]
    anchor: str              # "opening" when the printed opening balance seeds the chain
    closing_ok: bool | None  # None when the statement prints no closing balance

    @property
    def verified(self) -> int:
        return sum(s == VERIFIED for s in self.statuses)

    @property
    def unchecked(self) -> int:
        return sum(s == UNCHECKED for s in self.statuses)

    @property
    def clean(self) -> bool:
        return not self.breaks and self.closing_ok is not False


# ---------------------------------------------------------------- similarity

def _edit_distance_le1(a: str, b: str) -> bool:
    """True when b is a one-character edit of a, or an adjacent transposition."""
    if a == b:
        return False
    la, lb = len(a), len(b)
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    if abs(la - lb) != 1:
        return False
    short, long_ = (a, b) if la < lb else (b, a)
    for i in range(len(long_)):
        if long_[:i] + long_[i + 1:] == short:
            return True
    return False


def digits_similar(a: int, b: int) -> bool:
    """Could one amount be a misread of the other?

    A single digit substituted, dropped, doubled or swapped with its neighbour,
    or the decimal point shifted one or two places. These are the errors that
    text extraction and OCR actually make; an arbitrary amount is not.
    """
    a, b = abs(a), abs(b)
    if a == b or a == 0 or b == 0:
        return False
    if _edit_distance_le1(str(a), str(b)):
        return True
    hi, lo = max(a, b), min(a, b)
    return hi in (lo * 10, lo * 100)


# ---------------------------------------------------------------- the walk

def _next_checked(txns: list[Transaction], start: int) -> tuple[int | None, int]:
    """Position of the next row at or after `start` that prints a balance, and
    the summed net of unbalanced rows skipped on the way (not including it)."""
    carried = 0
    for j in range(start, len(txns)):
        if txns[j].balance is not None:
            return j, carried
        carried += txns[j].net
    return None, carried


def _window_closes(st: Statement, i: int, balance_i: int) -> bool:
    """If row i's balance were `balance_i`, would the chain close at the next check?"""
    txns = st.transactions
    j, carried = _next_checked(txns, i + 1)
    if j is None:
        if st.closing_balance is None:
            return False  # nothing downstream can confirm it
        return balance_i + carried == st.closing_balance
    return balance_i + carried + txns[j].net == txns[j].balance


def _hypotheses(st: Statement, i: int, prev: int, prev_row: int | None, prev_computed: int | None) -> list[Hypothesis]:
    t = st.transactions[i]
    printed = t.balance
    out: list[Hypothesis] = []
    need = printed - prev  # the net movement the printed balance demands
    # A fix to this row's amount leaves its printed balance in place, so the
    # row below must still agree with that printed balance for the fix to hold.
    downstream_ok = _window_closes(st, i, printed)

    # 1. Amount in the wrong column.
    one_sided = (t.debit or 0) == 0 or (t.credit or 0) == 0
    if one_sided and t.net != 0 and -t.net == need:
        out.append(Hypothesis(
            SWAP, i, {"debit": t.credit, "credit": t.debit}, downstream_ok,
            f"{fmt_inr(abs(t.net))} is a {'credit' if t.net < 0 else 'debit'}, not a {'debit' if t.net < 0 else 'credit'}",
        ))

    # 2. A digit misread in the amount. Same direction, a nearby number.
    if one_sided and t.net != 0 and need != 0 and (need > 0) == (t.net > 0) and digits_similar(t.net, need):
        side = "credit" if t.net > 0 else "debit"
        out.append(Hypothesis(
            AMOUNT, i, {side: abs(need)}, downstream_ok,
            f"{side} reads {fmt_inr(abs(t.net))}; the balances need {fmt_inr(abs(need))}",
        ))

    # 3. A digit misread in this row's balance. Only real if the row below agrees
    #    with the corrected figure instead of the printed one.
    corrected = prev + t.net
    if _window_closes(st, i, corrected):
        out.append(Hypothesis(
            BALANCE, i, {"balance": corrected}, True,
            f"balance reads {fmt_inr(printed)}; the chain gives {fmt_inr(corrected)}",
        ))

    # 3b. The previous row's balance was the misread one, and this break is its echo.
    if prev_row is not None and prev_computed is not None and prev_computed + t.net == printed:
        out.append(Hypothesis(
            BALANCE, prev_row, {"balance": prev_computed}, True,
            f"row above: balance should be {fmt_inr(prev_computed)}",
        ))

    # 4. A whole row missing. Arithmetically this explains any isolated break,
    #    which is exactly why it is never applied automatically.
    gap = printed - (prev + t.net)
    if gap != 0:
        out.append(Hypothesis(
            MISSING, i, {"insert_before": i, "net": gap}, downstream_ok,
            f"a {'credit' if gap > 0 else 'debit'} of {fmt_inr(abs(gap))} may be missing above this row",
        ))
    return out


def verify(st: Statement) -> ChainReport:
    """Walk the chain, set each transaction's status, and return the report."""
    txns = st.transactions
    statuses = [UNCHECKED] * len(txns)
    breaks: list[Break] = []

    first = next((k for k, t in enumerate(txns) if t.balance is not None), None)
    if st.opening_balance is not None:
        prev, anchor, start = st.opening_balance, "opening", 0
    elif first is not None:
        # No opening balance printed: the first balanced row seeds the chain.
        # It cannot be proven itself, so it stays unchecked.
        t = txns[first]
        prev, anchor, start = t.balance, "first_row", first + 1
        note = "no opening balance printed; first row is the anchor and is not proven"
        if note not in st.warnings:
            st.warnings.append(note)
    else:
        for t in txns:
            t.status = UNCHECKED
        return ChainReport(statuses, [], "none", None)

    pending: list[int] = []          # unbalanced rows waiting for the next check
    prev_row: int | None = None      # last row that printed a balance
    prev_computed: int | None = None # what that row's balance should have been, if it broke

    for i in range(start, len(txns)):
        t = txns[i]
        if t.balance is None:
            pending.append(i)
            continue
        carried = sum(txns[k].net for k in pending)
        expected = prev + carried + t.net
        if expected == t.balance:
            statuses[i] = VERIFIED
            prev_computed = None
        else:
            statuses[i] = BROKEN
            brk = Break(i, prev + carried, expected, t.balance)
            brk.hypotheses = _hypotheses(st, i, prev + carried, prev_row, prev_computed)
            breaks.append(brk)
            prev_computed = expected
        pending.clear()
        prev, prev_row = t.balance, i  # resync on what is printed

    closing_ok = None
    if st.closing_balance is not None:
        carried = sum(txns[k].net for k in pending)
        closing_ok = prev + carried == st.closing_balance

    for t, s in zip(txns, statuses):
        t.status = s
    return ChainReport(statuses, breaks, anchor, closing_ok)
