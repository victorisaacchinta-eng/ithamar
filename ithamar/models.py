"""Data model. All money is integer paise."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Row states, in the order a reader should trust them.
VERIFIED = "verified"    # proven by the chain exactly as printed
REPAIRED = "repaired"    # proven only after one logged correction; needs a glance
BROKEN = "broken"        # the chain does not close here and no single correction explains it
UNCHECKED = "unchecked"  # the statement prints no balance on this row, so nothing can be proven


@dataclass
class Transaction:
    index: int
    date: str | None
    narration: str
    debit: int | None
    credit: int | None
    balance: int | None
    value_date: str | None = None
    ref: str = ""
    page: int = 0
    status: str = UNCHECKED

    @property
    def net(self) -> int:
        return (self.credit or 0) - (self.debit or 0)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Statement:
    transactions: list[Transaction]
    opening_balance: int | None = None
    closing_balance: int | None = None
    source: str = ""
    bank: str = ""
    warnings: list[str] = field(default_factory=list)

    def copy(self) -> Statement:
        return Statement(
            transactions=[Transaction(**t.to_dict()) for t in self.transactions],
            opening_balance=self.opening_balance,
            closing_balance=self.closing_balance,
            source=self.source,
            bank=self.bank,
            warnings=list(self.warnings),
        )
