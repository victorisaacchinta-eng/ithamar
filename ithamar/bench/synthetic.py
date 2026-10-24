"""Synthetic Indian bank statements whose truth is known by construction.

Three layouts modelled on common Indian statement shapes (separate
withdrawal/deposit columns, debit/credit with wrapped descriptions, a single
amount column with Dr/Cr), page breaks with repeated headers, Indian digit
grouping, and realistic narration formats. Every bank, person and merchant
is fictional.

Errors are injected into what is PRINTED, never into the truth, so a
benchmark can measure exactly what the verifier catches and what it misses.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ithamar.money import fmt_inr

FIRST = ["Ravi", "Anjali", "Suresh", "Priya", "Kiran", "Meera", "Arjun", "Divya", "Naveen", "Lakshmi",
         "Rahul", "Sneha", "Vikram", "Asha", "Joseph", "Ruth", "Daniel", "Grace", "Imran", "Farah"]
LAST = ["Reddy", "Sharma", "Rao", "Nair", "Iyer", "Kumar", "Das", "Varghese", "Patel", "Khan", "Joshi", "Menon"]
MERCHANTS = ["KIRANA CORNER", "DECCAN FUELS", "CHARMINAR TRADERS", "GOLCONDA OPTICALS", "LOTUS PHARMACY",
             "NIZAM BAKERY", "TANK BUND STATIONERS", "BANJARA FURNISHINGS", "HITEC CITY CAFE", "MOOSI HARDWARE"]
COMPANIES = ["ASHOKA INFRA PVT LTD", "KONARK LOGISTICS", "MERIDIAN SOFTWARE LLP", "SHEFELAH INTERIORS"]
HANDLES = ["okaxis", "oksbi", "okhdfcbank", "ybl", "paytm", "ibl", "upi"]
BANK_CODES = ["ASHK", "KONK", "MRDN", "SHFL", "TANK"]
CITIES = ["HYDERABAD", "SECUNDERABAD", "WARANGAL", "VIJAYAWADA"]


@dataclass
class Row:
    date: str
    narration: str
    ref: str
    debit: int | None
    credit: int | None
    balance: int


@dataclass
class Truth:
    layout: str
    bank: str
    opening_balance: int
    closing_balance: int
    rows: list[Row]                       # what really happened
    printed: list[Row]                    # what the PDF shows (errors injected, missing rows dropped)
    injected: list[dict] = field(default_factory=list)  # {"kind", "truth_row", "printed_row"}

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1)

    @staticmethod
    def load(path: str | Path) -> Truth:
        d = json.loads(Path(path).read_text())
        d["rows"] = [Row(**r) for r in d["rows"]]
        d["printed"] = [Row(**r) for r in d["printed"]]
        return Truth(**d)


def _person(r: random.Random) -> str:
    return f"{r.choice(FIRST)} {r.choice(LAST)}"


def _narration(r: random.Random, credit: bool) -> tuple[str, str]:
    kind = r.choices(["upi", "neft", "imps", "atm", "pos", "ach", "chq", "int", "chg"],
                     weights=[9, 3, 2, 2, 3, 1, 1, 0.4, 0.4])[0]
    rrn = "".join(r.choice("0123456789") for _ in range(12))
    if kind == "int":
        return "INT.PD:SB INTEREST CREDIT", ""
    if kind == "chg":
        return r.choice(["SMS ALERT CHARGES QTR", "GST ON CHGS", "DEBIT CARD AMC CHARGES"]), ""
    if kind == "atm" and not credit:
        return f"ATM WDL/{r.randint(100000, 999999)}/{r.choice(CITIES)}", ""
    if kind == "pos" and not credit:
        return f"POS {r.randint(4000, 4999)}XXXXXXXX{r.randint(1000, 9999)} {r.choice(MERCHANTS)}", ""
    if kind == "ach" and not credit:
        return f"ACH D- {r.choice(COMPANIES)}-{r.randint(1000000, 9999999)}", ""
    if kind == "chq":
        no = f"{r.randint(0, 999999):06d}"
        return (f"CHQ DEP-{no}-{_person(r).upper()}" if credit else f"CHQ PAID-{no}-{_person(r).upper()}"), no
    if kind == "neft":
        code = r.choice(BANK_CODES)
        ifsc = f"{code}0{r.randint(100000, 999999)}"
        utr = f"{code}N{r.randint(10, 99)}{r.randint(10**9, 10**10 - 1)}"
        who = r.choice(COMPANIES) if credit else _person(r).upper()
        return (f"NEFT CR-{ifsc}-{who}-{utr}" if credit else f"NEFT DR-{ifsc}-{who}-{utr}"), utr[-10:]
    if kind == "imps":
        return f"IMPS/P2A/{rrn}/{_person(r).upper()}/{r.choice(BANK_CODES)}", rrn[-6:]
    who = _person(r)
    vpa = f"{who.split()[0].lower()}.{who.split()[1].lower()}@{r.choice(HANDLES)}"
    if not credit and r.random() < 0.5:
        m = r.choice(MERCHANTS)
        vpa = f"{m.split()[0].lower()}{r.randint(10, 99)}@{r.choice(HANDLES)}"
        who = m
    purpose = r.choice(["PAYMENT", "RENT", "GROCERIES", "FEES", "TRANSFER", "SHARED BILL"])
    return f"UPI/{rrn}/{purpose}/{vpa}/{who.upper()}", rrn[-6:]


def make_rows(seed: int, n: int, start: date = date(2026, 4, 1)) -> tuple[int, list[Row]]:
    r = random.Random(seed)
    opening = r.randint(5_000_00, 3_50_000_00)
    bal = opening
    rows: list[Row] = []
    d = start
    for _ in range(n):
        d += timedelta(days=r.choice([0, 0, 1, 1, 2, 3]))
        credit = r.random() < 0.3 or bal < 2_000_00
        if credit:
            amt = r.choice([r.randint(500_00, 25_000_00), r.randint(25_000_00, 1_80_000_00)])
        else:
            small = r.randint(20_00, 2_500_00)
            big_cap = min(60_000_00, bal - 1_000_00)
            amt = r.randint(2_500_00, big_cap) if big_cap > 2_500_00 and r.random() < 0.5 else small
            amt = min(amt, max(bal - 1_00, 1_00))
        narration, ref = _narration(r, credit)
        bal = bal + amt if credit else bal - amt
        rows.append(Row(d.isoformat(), narration, ref, None if credit else amt, amt if credit else None, bal))
    return opening, rows


def _flip_digit(r: random.Random, paise: int) -> int:
    s = list(str(paise))
    for _ in range(20):
        k = r.randrange(len(s))
        new = r.choice([c for c in "0123456789" if c != s[k]])
        if k == 0 and new == "0":
            continue
        s[k] = new
        return int("".join(s))
    return paise + 900


def inject(seed: int, rows: list[Row], kinds: list[str]) -> tuple[list[Row], list[dict]]:
    """Corrupt the printed copy. Targets are spaced so each break is its own window."""
    r = random.Random(seed * 7919 + 1)
    printed = [Row(**asdict(x)) for x in rows]
    slots = list(range(3, len(rows) - 3, 5))
    r.shuffle(slots)
    targets = sorted(slots[: len(kinds)])
    record = []
    for kind, t in zip(kinds, targets):
        row = printed[t]
        if kind == "swap":
            row.debit, row.credit = row.credit, row.debit
        elif kind == "amount":
            if row.debit:
                row.debit = _flip_digit(r, row.debit)
            else:
                row.credit = _flip_digit(r, row.credit)
        elif kind == "balance":
            row.balance = _flip_digit(r, row.balance)
        record.append({"kind": kind, "truth_row": t})
    # Delete missing rows last, from the bottom, so earlier indices stay valid.
    for rec in sorted(record, key=lambda x: -x["truth_row"]):
        if rec["kind"] == "missing":
            del printed[rec["truth_row"]]
    # Map each injection to its position in the printed list.
    for rec in record:
        t = rec["truth_row"]
        removed_above = sum(1 for x in record if x["kind"] == "missing" and x["truth_row"] < t)
        rec["printed_row"] = t - removed_above  # for "missing": the row that now follows the gap
    return printed, record


# ---------------------------------------------------------------- rendering

LAYOUTS = {
    "ashoka": {
        "bank": "ASHOKA LEDGER BANK",
        "cols": [("Date", 40, "l", 46), ("Narration", 90, "l", 190), ("Chq./Ref.No.", 290, "l", 60),
                 ("Value Dt", 356, "l", 44), ("Withdrawal Amt.", 470, "r", 0), ("Deposit Amt.", 540, "r", 0),
                 ("Closing Balance", 615, "r", 0)],
        "date": lambda d: date.fromisoformat(d).strftime("%d/%m/%y"),
        "pagesize": "landscape",
        "rows_per_page": 22,
    },
    "konark": {
        "bank": "KONARK SAHAKARI BANK",
        "cols": [("Txn Date", 36, "l", 50), ("Value Date", 92, "l", 50), ("Description", 150, "l", 150),
                 ("Ref No./Cheque No.", 306, "l", 70), ("Debit", 448, "r", 0), ("Credit", 506, "r", 0),
                 ("Balance", 566, "r", 0)],
        "date": lambda d: date.fromisoformat(d).strftime("%d %b %Y"),
        "pagesize": "portrait",
        "rows_per_page": 18,
    },
    "meridian": {
        "bank": "MERIDIAN UNION BANK",
        "cols": [("Date", 36, "l", 60), ("Particulars", 104, "l", 230), ("Amount", 430, "r", 0),
                 ("Dr/Cr", 446, "l", 30), ("Balance", 562, "r", 0)],
        "date": lambda d: date.fromisoformat(d).strftime("%d-%b-%Y"),
        "pagesize": "portrait",
        "rows_per_page": 24,
    },
}


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Wrap like a bank's statement printer: at spaces or slashes, and mid-token if a token is too wide."""
    import re as _re

    from reportlab.pdfbase.pdfmetrics import stringWidth
    tokens = [t for t in _re.split(r"(?<=[/ ])", text) if t]
    lines, cur = [], ""
    for tok in tokens:
        if stringWidth(cur + tok, font, size) <= width:
            cur += tok
            continue
        if cur:
            lines.append(cur.rstrip())
            cur = ""
        while stringWidth(tok, font, size) > width:
            k = len(tok)
            while k > 1 and stringWidth(tok[:k], font, size) > width:
                k -= 1
            lines.append(tok[:k])
            tok = tok[k:]
        cur = tok
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [""]


def render(path: str | Path, layout: str, opening: int, printed: list[Row], closing: int) -> None:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    spec = LAYOUTS[layout]
    size = landscape(A4) if spec["pagesize"] == "landscape" else A4
    W, H = size
    c = canvas.Canvas(str(path), pagesize=size)
    font, bold = "Helvetica", "Helvetica-Bold"
    pages = [printed[i:i + spec["rows_per_page"]] for i in range(0, len(printed), spec["rows_per_page"])] or [[]]
    first_date = printed[0].date if printed else "2026-04-01"
    last_date = printed[-1].date if printed else first_date

    for pno, chunk in enumerate(pages):
        y = H - 40
        if pno == 0:
            c.setFont(bold, 13)
            c.drawString(36, y, spec["bank"])
            y -= 16
            c.setFont(font, 8)
            c.drawString(36, y, "Synthetic specimen statement. Fictional bank, branch and people.")
            y -= 12
            c.drawString(36, y, f"Account Holder: {['N. Joseph', 'R. Daniel', 'G. Varghese'][len(printed) % 3]}    "
                                f"Account No: XXXXXXXX{(len(printed) * 37) % 10000:04d}")
            y -= 12
            c.drawString(36, y, f"Statement Period: {date.fromisoformat(first_date).strftime('%d %b %Y')} to "
                                f"{date.fromisoformat(last_date).strftime('%d %b %Y')}")
            y -= 12
            if layout != "konark":
                c.drawString(36, y, f"Opening Balance: {fmt_inr(opening)}")
                y -= 12
            y -= 10
        # Header row (repeated on every page).
        c.setFont(bold, 7.5)
        for name, x, align, _w in spec["cols"]:
            (c.drawRightString if align == "r" else c.drawString)(x, y, name)
        c.line(32, y - 4, W - 32, y - 4)
        y -= 16
        c.setFont(font, 7.5)
        if pno == 0 and layout == "konark":
            c.drawString(spec["cols"][2][1], y, "OPENING BALANCE")
            c.drawRightString(spec["cols"][6][1], y, fmt_inr(opening))
            y -= 13

        for row in chunk:
            ds = spec["date"](row.date)
            narr_w = next(w for n, x, a, w in spec["cols"] if n in ("Narration", "Description", "Particulars"))
            narr_lines = wrap(row.narration, font, 7.5, narr_w)
            for name, x, align, w in spec["cols"]:
                val = ""
                if name in ("Date", "Txn Date") or name in ("Value Dt", "Value Date"):
                    val = ds
                elif name in ("Narration", "Description", "Particulars"):
                    val = narr_lines[0]
                elif name.startswith(("Chq", "Ref")):
                    val = row.ref
                elif name in ("Withdrawal Amt.", "Debit"):
                    val = fmt_inr(row.debit) if row.debit else ""
                elif name in ("Deposit Amt.", "Credit"):
                    val = fmt_inr(row.credit) if row.credit else ""
                elif name == "Amount":
                    val = fmt_inr(row.debit or row.credit)
                elif name == "Dr/Cr":
                    val = "Dr" if row.debit else "Cr"
                elif name in ("Closing Balance", "Balance"):
                    val = fmt_inr(row.balance) + (" Cr" if layout == "meridian" else "")
                if val:
                    (c.drawRightString if align == "r" else c.drawString)(x, y, val)
            for extra in narr_lines[1:]:
                y -= 9
                c.drawString(next(x for n, x, a, w in spec["cols"] if n in ("Narration", "Description", "Particulars")), y, extra)
            y -= 13
        c.setFont(font, 7)
        if pno == len(pages) - 1:
            y -= 6
            c.drawString(36, y, f"Closing Balance: {fmt_inr(closing)}")
        c.drawString(36, 24, f"Page {pno + 1} of {len(pages)}")
        c.showPage()
    c.save()


def generate(out_dir: str | Path, seed: int, layout: str | None = None, n: int = 36,
             kinds: list[str] | None = None) -> tuple[Path, Truth]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    r = random.Random(seed)
    layout = layout or list(LAYOUTS)[seed % len(LAYOUTS)]
    if kinds is None:
        kinds = r.choice([[], [], ["swap"], ["amount"], ["balance", "swap"], ["amount", "missing", "swap"]])
    opening, rows = make_rows(seed, n)
    if not any(name.startswith(("Chq", "Ref")) for name, *_ in LAYOUTS[layout]["cols"]):
        for row in rows:
            row.ref = ""  # this layout prints no reference column
    printed, record = inject(seed, rows, kinds)
    closing = rows[-1].balance
    tag = "-".join(kinds) if kinds else "clean"
    pdf = out / f"synthetic_{seed:02d}_{layout}_{tag}.pdf"
    render(pdf, layout, opening, printed, closing)
    truth = Truth(layout, LAYOUTS[layout]["bank"], opening, closing, rows, printed, record)
    pdf.with_suffix(".truth.json").write_text(truth.to_json())
    return pdf, truth
