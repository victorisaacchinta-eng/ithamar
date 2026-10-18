"""Indian money parsing. Every amount becomes integer paise; floats never touch money.

Handles lakh grouping (1,00,000.00), western grouping (100,000.00), trailing
Dr/Cr markers, parentheses for negatives, a leading minus and the INR/Rs prefix.
"""

from __future__ import annotations

import re

_AMOUNT = re.compile(
    r"""^\(?                     # optional opening parenthesis
        (?:INR|Rs\.?|₹)?\s* # optional currency prefix
        (-)?                     # optional minus
        (\d{1,3}(?:,\d{2,3})*|\d+)  # integer part, any comma grouping
        \.(\d{2})                # exactly two decimals: refs and cheque numbers never have them
        \)?                      # optional closing parenthesis
        \s*(Cr|Dr|CR|DR|cr|dr)?\.?$""",
    re.VERBOSE,
)


class AmountError(ValueError):
    pass


def looks_like_amount(text: str) -> bool:
    return bool(_AMOUNT.match(text.strip()))


def parse_amount(text: str) -> tuple[int, str | None]:
    """Return (paise, marker) where marker is 'Dr', 'Cr' or None.

    The sign of the returned paise reflects a leading minus or parentheses only.
    Dr/Cr meaning depends on the column, so the caller decides what it implies.
    """
    raw = text.strip()
    m = _AMOUNT.match(raw)
    if not m:
        raise AmountError(f"not an amount: {text!r}")
    minus, whole, frac, marker = m.groups()
    paise = int(whole.replace(",", "")) * 100 + int(frac)
    if minus or raw.startswith("("):
        paise = -paise
    return paise, (marker.capitalize() if marker else None)


def fmt_inr(paise: int | None) -> str:
    """Format paise in Indian grouping: 123456789 -> '12,34,567.89'."""
    if paise is None:
        return ""
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    whole, frac = divmod(paise, 100)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{sign}{s}.{frac:02d}"
