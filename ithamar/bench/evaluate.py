"""Score the engine against statements whose truth is known.

Headline metric: FALSE-VERIFIED rows. A row marked verified or repaired whose
values differ from the truth. It must stay at zero; everything else is detail.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ithamar.bench.synthetic import Truth
from ithamar.models import REPAIRED, VERIFIED
from ithamar.parse import parse_pdf
from ithamar.verify import repair


@dataclass
class Score:
    file: str
    rows: int
    extracted_exact: int   # rows the parser read exactly as printed
    verified: int          # proven as printed
    repaired: int          # proven after one logged correction
    repaired_correct: int  # repaired rows that now equal the truth
    injected: int
    caught: int            # injected errors the engine did not mark as proven-as-printed
    false_verified: int    # proven rows that are wrong: must be zero
    closing_ok: bool | None


def _same(a, b) -> bool:
    return (a.debit or 0, a.credit or 0, a.balance) == (b.debit or 0, b.credit or 0, b.balance)


def score(pdf: str | Path) -> Score:
    pdf = Path(pdf)
    truth = Truth.load(pdf.with_suffix(".truth.json"))
    st = parse_pdf(pdf)
    norm = lambda s: s.replace(" ", "")
    exact = sum(
        1 for a, b in zip(st.transactions, truth.printed)
        if (a.date, a.debit, a.credit, a.balance, norm(a.narration)) == (b.date, b.debit, b.credit, b.balance, norm(b.narration))
    )
    res = repair(st)
    out = res.statement.transactions

    # Map printed rows back to truth rows (missing rows shift indices).
    gaps = sorted(r["truth_row"] for r in truth.injected if r["kind"] == "missing")
    to_truth, shift = [], 0
    for p in range(len(truth.printed)):
        while shift < len(gaps) and gaps[shift] <= p + shift:
            shift += 1
        to_truth.append(p + shift)

    injected_rows = {r["printed_row"]: r for r in truth.injected}
    caught = sum(1 for p in injected_rows if p < len(out) and out[p].status != VERIFIED)
    false_verified = repaired_correct = 0
    for p, t in enumerate(out):
        if p >= len(to_truth):
            break
        tr = truth.rows[to_truth[p]]
        if t.status in (VERIFIED, REPAIRED) and not _same(t, tr):
            false_verified += 1
        if t.status == REPAIRED and _same(t, tr):
            repaired_correct += 1
    return Score(pdf.name, len(out), exact, sum(t.status == VERIFIED for t in out),
                 sum(t.status == REPAIRED for t in out), repaired_correct, len(truth.injected),
                 caught, false_verified, res.report.closing_ok)


def bench(folder: str | Path) -> list[Score]:
    return [score(p) for p in sorted(Path(folder).glob("*.pdf")) if p.with_suffix(".truth.json").exists()]


def table(scores: list[Score]) -> str:
    head = ["file", "rows", "exact", "verified", "repaired", "fixed_ok", "injected", "caught", "false_verified", "closing_ok"]
    rows = [[s.file, s.rows, s.extracted_exact, s.verified, s.repaired, s.repaired_correct, s.injected,
             s.caught, s.false_verified, s.closing_ok] for s in scores]
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    fmt = lambda r: "  ".join(str(x).ljust(w) for x, w in zip(r, widths))
    lines = [fmt(head)] + [fmt(r) for r in rows]
    lines.append(f"false-verified rows across {len(scores)} statements: {sum(s.false_verified for s in scores)}")
    return "\n".join(lines)
