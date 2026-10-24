"""Repair: choose between explanations, and refuse when the choice is not earned.

The chain (chain.py) finds every break and lists the corrections that could
explain it. This module decides which, if any, to apply. The rules:

1. A candidate is only considered if applying it makes the local window close:
   the broken row AND the next row that prints a balance (or the printed
   closing balance) agree afterwards. Fixing one row while breaking the next
   is not a fix.
2. ``missing_row`` is NEVER applied. Arithmetically it explains any isolated
   break, so it proves nothing, and applying it would invent a transaction.
   It is reported with its suggested amount for a person to check.
3. A specific candidate (swap, amount misread, balance misread) is applied
   only when it is the ONLY specific candidate that closes. A missing row
   closing at the same time does not block it, because a missing row would
   have to carry exactly the amount the specific error predicts, which is a
   coincidence. That rejected alternative is logged, never hidden.
4. Two different specific candidates that both close: accept neither. The
   statement is ambiguous there and the row goes to a human.
5. One correction is applied at a time, then the whole chain is re-verified.
   A correction that does not strictly reduce the number of breaks is reverted.
6. Rows the engine corrected end as ``repaired``, never ``verified``. Proven
   after a change is a different claim from proven as printed, and the
   report keeps them apart.

Stretch (V2): when no rule closes the window, widen it, try merged or split
rows, then ask a local model (Ollama) for a JSON correction. The model's
answer is a hypothesis like any other: it must make the chain close.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ithamar.models import REPAIRED, VERIFIED, Statement
from ithamar.verify.chain import MISSING, Break, ChainReport, Hypothesis, verify

MAX_ROUNDS = 50


@dataclass
class Unresolved:
    row: int
    reason: str                        # "ambiguous" | "no_explanation" | "missing_row_suspected" | "unconfirmable"
    candidates: list[dict] = field(default_factory=list)


@dataclass
class RepairResult:
    statement: Statement
    report: ChainReport
    log: list[dict] = field(default_factory=list)
    unresolved_detail: list[Unresolved] = field(default_factory=list)

    @property
    def unresolved(self) -> list[int]:
        return sorted({u.row for u in self.unresolved_detail})

    @property
    def repaired_rows(self) -> list[int]:
        return sorted({e["row"] for e in self.log})


def _describe(h: Hypothesis) -> dict:
    return {"kind": h.kind, "row": h.row, "fix": dict(h.fix), "detail": h.detail}


def decide(brk: Break) -> tuple[Hypothesis | None, Unresolved | None, list[Hypothesis]]:
    """Return (accepted, unresolved, rejected_alternatives) for one break."""
    closing = list({h.key: h for h in brk.hypotheses if h.closes}.values())
    specific = [h for h in closing if h.kind != MISSING]
    missing = [h for h in closing if h.kind == MISSING]

    if len(specific) == 1:
        return specific[0], None, missing
    if len(specific) > 1:
        return None, Unresolved(brk.row, "ambiguous", [_describe(h) for h in specific + missing]), []
    if missing:
        return None, Unresolved(brk.row, "missing_row_suspected", [_describe(h) for h in missing]), []
    if brk.hypotheses:
        # Something would fix this row, but nothing below can confirm it
        # (typically the last row of a statement with no printed closing balance).
        return None, Unresolved(brk.row, "unconfirmable", [_describe(h) for h in brk.hypotheses]), []
    return None, Unresolved(brk.row, "no_explanation"), []


def _apply(st: Statement, h: Hypothesis) -> dict:
    """Apply a correction in place and return what it replaced."""
    t = st.transactions[h.row]
    before = {k: getattr(t, k) for k in h.fix}
    for k, v in h.fix.items():
        setattr(t, k, v)
    return before


def _undo(st: Statement, row: int, before: dict) -> None:
    t = st.transactions[row]
    for k, v in before.items():
        setattr(t, k, v)


def repair(statement: Statement, report: ChainReport | None = None) -> RepairResult:
    """Return a repaired COPY of the statement. The input is never mutated."""
    st = statement.copy()
    report = verify(st)
    log: list[dict] = []
    parked: dict[int, Unresolved] = {}   # rows a person has to look at

    for _ in range(MAX_ROUNDS):
        progressed = False
        for brk in report.breaks:
            if brk.row in parked:
                continue
            accepted, unresolved, rejected = decide(brk)
            if accepted is None:
                parked[brk.row] = unresolved
                continue

            before_breaks = len(report.breaks)
            before = _apply(st, accepted)
            trial = verify(st)
            if len(trial.breaks) >= before_breaks:
                _undo(st, accepted.row, before)
                parked[brk.row] = Unresolved(brk.row, "no_explanation", [_describe(accepted)])
                report = verify(st)
                continue

            log.append({
                "row": accepted.row,
                "break_at": brk.row,
                "kind": accepted.kind,
                "before": before,
                "after": dict(accepted.fix),
                "detail": accepted.detail,
                "rejected": [_describe(h) for h in rejected],
            })
            report = trial
            progressed = True
            break  # breaks moved; start again from the fresh report
        if not progressed:
            break

    report = verify(st)
    # A parked row may have been fixed as a side effect of a later correction.
    live = {b.row for b in report.breaks}
    unresolved = [u for r, u in sorted(parked.items()) if r in live]
    for b in report.breaks:
        if b.row not in parked:
            unresolved.append(Unresolved(b.row, "no_explanation"))

    touched = {e["row"] for e in log}
    for k, t in enumerate(st.transactions):
        if k in touched and t.status == VERIFIED:
            t.status = REPAIRED
            report.statuses[k] = REPAIRED

    return RepairResult(st, report, log, unresolved)
