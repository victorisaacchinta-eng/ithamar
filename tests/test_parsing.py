import pytest

from ithamar.dates import parse_date
from ithamar.money import AmountError, fmt_inr, looks_like_amount, parse_amount
from ithamar.narration import decode
from ithamar.parse.layout import classify, join_wrapped


@pytest.mark.parametrize("text,paise,marker", [
    ("1,00,000.00", 10_000_000, None),
    ("100,000.00", 10_000_000, None),
    ("12.50", 1250, None),
    ("2,45,670.05 Cr", 24_567_005, "Cr"),
    ("3,210.00Dr", 321_000, "Dr"),
    ("(1,234.00)", -123_400, None),
    ("-45.10", -4510, None),
    ("Rs. 500.00", 50_000, None),
    ("₹1,250.00", 125_000, None),
])
def test_amounts(text, paise, marker):
    assert parse_amount(text) == (paise, marker)


@pytest.mark.parametrize("text", ["000123456789", "412345", "2026", "12.5", "abc", "", "1,2,3"])
def test_not_amounts(text):
    assert not looks_like_amount(text)
    with pytest.raises(AmountError):
        parse_amount(text)


def test_fmt_inr_lakh_grouping():
    assert fmt_inr(123_456_789) == "12,34,567.89"
    assert fmt_inr(100) == "1.00"
    assert fmt_inr(-5_00_000_00) == "-5,00,000.00"
    assert fmt_inr(None) == ""


@pytest.mark.parametrize("text,iso", [
    ("03/04/2026", "2026-04-03"),   # day first, always
    ("03/04/26", "2026-04-03"),
    ("05 Oct 2026", "2026-10-05"),
    ("05-Oct-2026", "2026-10-05"),
    ("2026-10-05", "2026-10-05"),
    ("31/02/2026", None),
])
def test_dates(text, iso):
    assert parse_date(text) == iso


def test_date_without_year_uses_statement_year():
    assert parse_date("05 Oct", 2026) == "2026-10-05"
    assert parse_date("05 Oct") is None


@pytest.mark.parametrize("header,field", [
    ("Withdrawal Amt.", "debit"), ("Deposit Amt.", "credit"), ("Closing Balance", "balance"),
    ("Chq./Ref.No.", "ref"), ("Value Dt", "value_date"), ("Txn Date", "date"),
    ("Particulars", "narration"), ("Dr/Cr", "dir"), ("Amount", "amount"), ("Description", "narration"),
])
def test_header_classification(header, field):
    assert classify(header) == field


def test_wrapped_narration_join():
    assert join_wrapped("UPI/1234/PAYMENT/", "ravi@okaxis") == "UPI/1234/PAYMENT/ravi@okaxis"
    assert join_wrapped("NEFT CR", "KONARK LOGISTICS") == "NEFT CR KONARK LOGISTICS"


def test_decode_upi():
    d = decode("UPI/412345678901/RENT/ravi.kumar@okaxis/RAVI KUMAR")
    assert (d.rail, d.rrn, d.vpa) == ("UPI", "412345678901", "ravi.kumar@okaxis")
    assert d.counterparty == "Ravi Kumar"


def test_decode_neft():
    d = decode("NEFT CR-KONK0123456-MERIDIAN SOFTWARE LLP-KONKN521234567890")
    assert d.rail == "NEFT"
    assert d.ifsc == "KONK0123456"
    assert d.utr == "KONKN521234567890"
    assert d.counterparty == "Meridian Software Llp"


def test_decode_other_rails():
    assert decode("ATM WDL/123456/HYDERABAD").rail == "ATM"
    assert decode("POS 4123XXXXXXXX9876 LOTUS PHARMACY").rail == "CARD"
    assert decode("CHQ PAID-004521-GRACE NAIR").cheque == "004521"
    assert decode("INT.PD:SB INTEREST CREDIT").rail == "INTEREST"
    assert decode("GST ON CHGS").rail == "CHARGES"
