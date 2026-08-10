"""Shared helpers: phone validation/formatting, KES formatting, IDs."""
import re
import secrets
from datetime import datetime

# 7XXXXXXXX | 07XXXXXXXX | 2547XXXXXXXX | +2547XXXXXXXX
_PHONE_RE = re.compile(r"^(?:\+?254|0)?7\d{8}$")


def normalize_phone(raw):
    """Return normalized '2547XXXXXXXX' or None if invalid."""
    digits = re.sub(r"\D", "", raw or "")
    if re.fullmatch(r"7\d{8}", digits):
        return "254" + digits
    if re.fullmatch(r"07\d{8}", digits):
        return "254" + digits[1:]
    if re.fullmatch(r"2547\d{8}", digits):
        return digits
    return None


def format_phone(phone):
    p = str(phone or "")
    if len(p) == 12 and p.startswith("2547"):
        return f"+254 7{p[4:6]} {p[6:9]} {p[9:]}"
    return p


def format_ksh(n):
    return f"KES {int(n):,}"


def generate_application_number():
    return f"LP-{datetime.utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}"