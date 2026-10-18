"""Turn a statement PDF into transactions using word geometry.

No bank templates. The parser finds the header row, learns where each column
sits from the header words, then assigns every word below it by position:
amounts align to the RIGHT edge of their column, text to the LEFT edge.
Lines without a date are continuations of the previous row's narration.

Whatever this gets wrong, the balance chain is there to catch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ithamar.dates import parse_date
from ithamar.models import Statement, Transaction
from ithamar.money import AmountError, looks_like_amount, parse_amount

# Order matters: the first match wins, so specific phrases come first.
FIELDS: list[tuple[str, tuple[str, ...]]] = [
    ("value_date", ("value date", "value dt", "val dt")),
    ("dir", ("dr cr", "cr dr", "dr/cr", "type")),
    ("ref", ("chq", "cheque", "ref", "reference", "instrument")),
    ("debit", ("withdrawal", "debit", "paid out", "dr amount")),
    ("credit", ("deposit", "credit", "paid in", "cr amount")),
    ("balance", ("balance",)),
    ("amount", ("amount",)),
    ("date", ("date", "txn dt", "tran dt", "txn date")),
    ("narration", ("narration", "description", "particulars", "remarks", "details", "transaction")),
]
NUMERIC = {"debit", "credit", "amount", "balance"}
_STOP = re.compile(r"page \d+ of \d+|end of statement|statement summary|this is a (computer|system)|\*\*\* end", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d{2})\b")
_OPENING = re.compile(r"opening\s+balance|balance\s+b/?f|brought\s+forward", re.IGNORECASE)
_CLOSING = re.compile(r"closing\s+balance|balance\s+c/?f|carried\s+forward", re.IGNORECASE)
_SUMMARY_AMT = re.compile(r"(\(?-?(?:INR|Rs\.?|₹)?\s*\d{1,3}(?:,\d{2,3})*\.\d{2}\)?(?:\s*(?:Cr|Dr|CR|DR))?)")


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    page: int


@dataclass
class Column:
    field: str
    x0: float
    x1: float


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def classify(header: str) -> str | None:
    h = " " + _norm(header) + " "
    for field, keys in FIELDS:
        for k in keys:
            if " " + _norm(k) + " " in h:
                return field
    return None


def lines_of(words: list[Word], tol: float = 3.0) -> list[list[Word]]:
    out: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.page, round(w.top, 1), w.x0)):
        if out and out[-1][0].page == w.page and abs(out[-1][0].top - w.top) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    for line in out:
        line.sort(key=lambda w: w.x0)
    return out


def merge_suffixes(line: list[Word]) -> list[Word]:
    """Glue a standalone 'Dr'/'Cr' onto the amount just before it."""
    merged: list[Word] = []
    for w in line:
        t = w.text.strip(".")
        if merged and t.lower() in ("dr", "cr") and looks_like_amount(merged[-1].text) and w.x0 - merged[-1].x1 < 8:
            p = merged[-1]
            merged[-1] = Word(f"{p.text} {t}", p.x0, w.x1, p.top, p.page)
        else:
            merged.append(w)
    return merged


def _header_columns(line: list[Word], gap: float = 7.0) -> list[Column] | None:
    """Group header words into cells by horizontal gap, then name each cell."""
    cells: list[list[Word]] = []
    for w in line:
        if cells and w.x0 - cells[-1][-1].x1 < gap:
            cells[-1].append(w)
        else:
            cells.append([w])
    cols = []
    for c in cells:
        field = classify(" ".join(w.text for w in c))
        if field:
            cols.append(Column(field, c[0].x0, c[-1].x1))
    names = {c.field for c in cols}
    has_money = bool(names & {"debit", "credit", "amount"})
    if "balance" in names and "date" in names and has_money:
        # Keep only the first column of each kind (a second "date" is a value date).
        seen, out = set(), []
        for c in cols:
            if c.field == "date" and "date" in seen:
                c = Column("value_date", c.x0, c.x1)
            if c.field not in seen:
                seen.add(c.field)
                out.append(c)
        return out
    return None


def _assign(line: list[Word], cols: list[Column]) -> dict[str, list[Word]]:
    cells: dict[str, list[Word]] = {c.field: [] for c in cols}
    numeric = [c for c in cols if c.field in NUMERIC]
    ordered = sorted(cols, key=lambda c: c.x0)
    for w in line:
        if numeric and looks_like_amount(w.text):
            best = min(numeric, key=lambda c: abs(c.x1 - w.x1))
            # Accept if right edges are close, or the word sits inside the column's span.
            if abs(best.x1 - w.x1) <= 40 or best.x0 - 4 <= w.x0 <= best.x1 + 4:
                cells[best.field].append(w)
                continue
        owner = None
        for c in ordered:
            if c.x0 <= w.x0 + 3:
                owner = c
        if owner is None:
            owner = ordered[0]
        if owner.field in NUMERIC:
            text_cols = [c for c in ordered if c.field not in NUMERIC and c.x0 <= w.x0 + 3]
            owner = text_cols[-1] if text_cols else ordered[0]
        cells[owner.field].append(w)
    return cells


def join_wrapped(head: str, tail: str) -> str:
    """Join a wrapped narration line. Printers break after '/' or '-' without a space."""
    if not head:
        return tail
    if head.endswith(("/", "-")) or tail.startswith(("/", "-")):
        return head + tail
    return f"{head} {tail}"


def _text(ws: list[Word]) -> str:
    return " ".join(w.text for w in ws).strip()


def _money(ws: list[Word]) -> tuple[int, str | None] | None:
    for w in ws:
        try:
            return parse_amount(w.text)
        except AmountError:
            continue
    return None


def _summary_amount(line_text: str) -> int | None:
    m = _SUMMARY_AMT.findall(line_text)
    if not m:
        return None
    paise, marker = parse_amount(m[-1])
    return -abs(paise) if marker == "Dr" else paise


def parse_words(words: list[Word], source: str = "") -> Statement:
    """Pure function: positioned words in, a Statement out. PDF-free so it can be tested."""
    all_text = " ".join(w.text for w in words)
    years = _YEAR.findall(all_text)
    default_year = int(years[0]) if years else None

    st = Statement(transactions=[], source=source)
    cols: list[Column] | None = None
    current: Transaction | None = None
    last_top: float | None = None
    last_page = -1
    in_table = False
    line_h = 12.0

    for raw in lines_of(words):
        line = merge_suffixes(raw)
        text = _text(line)
        page = line[0].page
        if page != last_page:
            in_table = cols is not None  # columns carry over if the header is not repeated
            last_top, last_page = None, page
            if not st.bank and page == 0 and text:
                st.bank = text if not st.bank else st.bank

        hdr = _header_columns(line)
        if hdr:
            cols, in_table, current, last_top = hdr, True, None, line[0].top
            continue

        if cols is None:
            # Above the table: look for printed opening and closing balances.
            if _OPENING.search(text) and st.opening_balance is None:
                st.opening_balance = _summary_amount(text)
            elif _CLOSING.search(text) and st.closing_balance is None:
                st.closing_balance = _summary_amount(text)
            continue

        if _STOP.search(text):
            in_table, current = False, None
            if _CLOSING.search(text) and st.closing_balance is None:
                st.closing_balance = _summary_amount(text)
            continue
        if not in_table:
            if _CLOSING.search(text) and st.closing_balance is None:
                st.closing_balance = _summary_amount(text)
            elif _OPENING.search(text) and st.opening_balance is None:
                st.opening_balance = _summary_amount(text)
            continue

        cells = _assign(line, cols)
        date_txt = _text(cells.get("date", []))
        dt = parse_date(date_txt, default_year) if date_txt else None
        narration = _text(cells.get("narration", []))

        if dt is None:
            # Opening / closing balance rows inside the table.
            if _OPENING.search(text) and st.opening_balance is None:
                bal = _money(cells.get("balance", []))
                if bal:
                    st.opening_balance = -abs(bal[0]) if bal[1] == "Dr" else bal[0]
                continue
            if _CLOSING.search(text):
                if st.closing_balance is None:
                    st.closing_balance = _summary_amount(text)
                in_table = False
                continue
            near = last_top is not None and line[0].top - last_top <= 2.4 * line_h
            if current is not None and near and not any(cells.get(f) for f in NUMERIC):
                extra = narration or text
                current.narration = join_wrapped(current.narration, extra)
                ref_extra = _text(cells.get("ref", []))
                if ref_extra and narration:
                    current.ref = f"{current.ref}{ref_extra}"
                last_top = line[0].top
            continue

        if _OPENING.search(narration) and not cells.get("debit") and not cells.get("credit") and not cells.get("amount"):
            bal = _money(cells.get("balance", []))
            if bal and st.opening_balance is None:
                st.opening_balance = -abs(bal[0]) if bal[1] == "Dr" else bal[0]
            continue

        debit = credit = None
        if cells.get("amount"):
            amt = _money(cells["amount"])
            if amt:
                marker = amt[1] or ("Dr" if _text(cells.get("dir", [])).lower().startswith("d") else
                                    "Cr" if _text(cells.get("dir", [])).lower().startswith("c") else None)
                if marker == "Dr" or amt[0] < 0:
                    debit = abs(amt[0])
                elif marker == "Cr":
                    credit = abs(amt[0])
                else:
                    st.warnings.append(f"row {len(st.transactions)}: amount without direction")
                    credit = abs(amt[0])
        if cells.get("debit"):
            m = _money(cells["debit"])
            debit = abs(m[0]) if m else None
        if cells.get("credit"):
            m = _money(cells["credit"])
            credit = abs(m[0]) if m else None
        bal = _money(cells.get("balance", []))
        balance = None
        if bal:
            balance = -abs(bal[0]) if bal[1] == "Dr" else bal[0]

        vd_txt = _text(cells.get("value_date", []))
        current = Transaction(
            index=len(st.transactions),
            date=dt,
            value_date=parse_date(vd_txt, default_year) if vd_txt else None,
            narration=narration,
            ref=_text(cells.get("ref", [])),
            debit=debit,
            credit=credit,
            balance=balance,
            page=page,
        )
        st.transactions.append(current)
        last_top = line[0].top

    if cols is None:
        st.warnings.append("no transaction table header found")
    return st


def words_from_pdf(path: str | Path, password: str | None = None) -> list[Word]:
    import pdfplumber

    out: list[Word] = []
    with pdfplumber.open(str(path), password=password or None) as pdf:
        for pno, page in enumerate(pdf.pages):
            for w in page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False):
                out.append(Word(w["text"], float(w["x0"]), float(w["x1"]), float(w["top"]), pno))
    return out


def parse_pdf(path: str | Path, password: str | None = None) -> Statement:
    return parse_words(words_from_pdf(path, password), source=str(path))
