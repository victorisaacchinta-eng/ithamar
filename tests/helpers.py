from ithamar.models import Statement, Transaction


def ledger(nets: list[int], opening: int = 10_000_00, closing: bool = True) -> Statement:
    """A correct statement from a list of net movements (positive = credit)."""
    bal = opening
    txns = []
    for i, n in enumerate(nets):
        bal += n
        txns.append(Transaction(i, f"2026-04-{(i % 28) + 1:02d}", f"ROW {i}",
                                debit=-n if n < 0 else None, credit=n if n > 0 else None, balance=bal))
    return Statement(txns, opening_balance=opening, closing_balance=bal if closing else None)
