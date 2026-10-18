"""Decode Indian bank narrations into rail, references and counterparty.

Narrations follow no standard; every bank writes them differently. Strict
identifiers (VPA, IFSC, 12-digit RRN, UTR, cheque number) use tight patterns.
The counterparty is best-effort and labelled as such. None of this is proven
by the balance chain: it is decoration on top of proven numbers.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_VPA = re.compile(r"\b([a-z0-9][a-z0-9.\-_]{1,63}@[a-z][a-z0-9]{1,30})\b", re.IGNORECASE)
_RRN = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_IFSC = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
_UTR = re.compile(r"\b([A-Z]{4}[RHN0-9]\d{2}[0-9A-Z]{8,15})\b")
_CHQ = re.compile(r"\b(?:CHQ|CHEQUE|CLG)\D{0,6}(\d{6})\b", re.IGNORECASE)

_RAILS = [
    ("UPI", re.compile(r"\bUPI\b", re.IGNORECASE)),
    ("IMPS", re.compile(r"\bIMPS\b|\bMMT\b", re.IGNORECASE)),
    ("NEFT", re.compile(r"\bNEFT\b", re.IGNORECASE)),
    ("RTGS", re.compile(r"\bRTGS\b", re.IGNORECASE)),
    ("ACH", re.compile(r"\bACH\b|\bNACH\b|\bECS\b", re.IGNORECASE)),
    ("ATM", re.compile(r"\bATM\b|\bATW\b|\bNWD\b|CASH WDL", re.IGNORECASE)),
    ("CARD", re.compile(r"\bPOS\b|\bECOM\b|\bVPS\b|\bIPS\b", re.IGNORECASE)),
    ("CHEQUE", re.compile(r"\bCHQ\b|\bCHEQUE\b|\bCLG\b", re.IGNORECASE)),
    ("INTEREST", re.compile(r"\bINT(?:EREST)?\.?\s*(?:CR|PD|PAID|CREDIT)\b|\bSB INT\b|\bINTEREST\b", re.IGNORECASE)),
    ("CHARGES", re.compile(r"\bCHGS?\b|\bCHARGES?\b|\bGST\b|\bFEE\b|\bAMC\b", re.IGNORECASE)),
    ("CASH", re.compile(r"\bCASH\s*(?:DEP|DEPOSIT)\b|\bBY CASH\b", re.IGNORECASE)),
]

_NOISE = {
    "UPI", "IMPS", "NEFT", "RTGS", "P2A", "P2M", "P2P", "CR", "DR", "PAYMENT", "TRANSFER",
    "TO", "FROM", "BY", "REF", "NA", "MMT", "ACH", "NACH", "D", "C", "INB",
}


@dataclass
class Decoded:
    rail: str = ""
    vpa: str = ""
    rrn: str = ""
    utr: str = ""
    ifsc: str = ""
    cheque: str = ""
    counterparty: str = ""  # best effort, never proven

    def to_dict(self) -> dict:
        return asdict(self)


def _counterparty(narration: str, d: Decoded) -> str:
    text = narration
    for ident in (d.vpa, d.rrn, d.utr, d.ifsc, d.cheque):
        if ident:
            text = text.replace(ident, " ")
    parts = [p.strip(" .:") for p in re.split(r"[/|-]", text)]
    if d.rail == "UPI":
        # UPI narrations end with the payee's name; a purpose like "RENT" sits earlier.
        parts = parts[::-1]
    best = ""
    for p in parts:
        words = [w for w in re.split(r"\s+", p) if w and w.upper() not in _NOISE]
        cand = " ".join(words)
        if not cand or any(ch.isdigit() for ch in cand) or "@" in cand:
            continue
        letters = sum(ch.isalpha() for ch in cand)
        if letters >= 3 and len(cand) > len(best):
            best = cand
            if d.rail == "UPI":
                break
    return best.title() if best.isupper() else best


def decode(narration: str) -> Decoded:
    n = narration or ""
    d = Decoded()
    for name, pat in _RAILS:
        if pat.search(n):
            d.rail = name
            break
    if m := _VPA.search(n):
        d.vpa = m.group(1).lower()
    if m := _RRN.search(n):
        d.rrn = m.group(1)
    if m := _IFSC.search(n):
        d.ifsc = m.group(1)
    if d.rail in ("NEFT", "RTGS", "IMPS"):
        for m in _UTR.finditer(n):
            if m.group(1) != d.ifsc:
                d.utr = m.group(1)
                break
    if m := _CHQ.search(n):
        d.cheque = m.group(1)
    if d.rail not in ("INTEREST", "CHARGES", "ATM"):
        d.counterparty = _counterparty(n, d)
    return d
