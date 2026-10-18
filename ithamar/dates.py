"""Day-first date parsing for Indian statements. Output is ISO yyyy-mm-dd.

Indian banks never print month-first, so 03/04/2026 is 3 April, always.
"""

from __future__ import annotations

import re
from datetime import date

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

_NUMERIC = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})$")
_NAMED = re.compile(r"^(\d{1,2})[\s\-/]?([A-Za-z]{3,9})[\s\-/,]*(\d{2}|\d{4})?$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _year(y: str | None, default_year: int | None) -> int | None:
    if y is None:
        return default_year
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_date(text: str, default_year: int | None = None) -> str | None:
    t = text.strip().rstrip(",")
    try:
        if m := _ISO.match(t):
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        if m := _NUMERIC.match(t):
            y = _year(m[3], default_year)
            return date(y, int(m[2]), int(m[1])).isoformat() if y else None
        if m := _NAMED.match(t):
            mon = _MONTHS.get(m[2][:3].lower())
            y = _year(m[3], default_year)
            if mon and y:
                return date(y, mon, int(m[1])).isoformat()
    except ValueError:
        return None
    return None


def looks_like_date(text: str, default_year: int | None = 2000) -> bool:
    """True if the text parses as a date. The default year lets '05 Oct' count."""
    return parse_date(text, default_year) is not None
