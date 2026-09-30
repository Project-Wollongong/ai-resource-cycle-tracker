"""Lossless normalizers for P03 reported facts.

Only explicit source tokens are normalized.  No currency, unit, date or project is
inferred from market convention.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date


_MONTHS = {
    name.casefold(): number
    for number, name in enumerate(
        ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    )
    if name
}


def number(raw: str) -> float | None:
    value = raw.strip().replace(",", "")
    negative = value.startswith("(") and value.endswith(")")
    value = value.strip("()")
    try:
        parsed = float(value)
    except ValueError:
        return None
    return -parsed if negative else parsed


def currency(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    token = raw.strip()
    folded = token.casefold().replace(" ", "")
    if folded in {"a$", "$a", "aud"}:
        return token, "AUD"
    if folded in {"us$", "$us", "usd"}:
        return token, "USD"
    if token == "$":
        return token, "unknown"
    return token, "unknown"


def unit(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    token = " ".join(raw.strip().split())
    folded = token.casefold().replace("’", "'")
    mapping = {
        "a$m": "AUD million", "a$ m": "AUD million", "$am": "AUD million",
        "$a'000": "AUD thousand", "$a’000": "AUD thousand", "a$'000": "AUD thousand",
        "$m": "million", "million dollars": "million", "dollars": "currency unit",
        "$/share": "currency unit per share", "$ / share": "currency unit per share",
        "shares": "shares", "%": "percent", "mt": "million tonnes", "kt": "thousand tonnes",
        "ktpa": "thousand tonnes per annum", "mtpa": "million tonnes per annum",
        "koz": "thousand ounces", "moz": "million ounces", "g/t": "grams per tonne",
        "g/t au": "grams per tonne gold", "koz au": "thousand ounces gold",
        "% li2o": "percent Li2O", "m": "metres", "ha": "hectares", "years": "years",
        "million": "million", "billion": "billion", "composites": "composites",
    }
    return token, mapping.get(folded, "unknown")


def explicit_date(raw: str) -> date | None:
    text = " ".join(raw.strip().split())
    iso = re.fullmatch(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    named = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", text)
    if named and named.group(2).casefold() in _MONTHS:
        try:
            return date(int(named.group(3)), _MONTHS[named.group(2).casefold()], int(named.group(1)))
        except ValueError:
            return None
    return None


def period_range(raw: str) -> tuple[date | None, date | None, str | None]:
    """Return an explicit range plus the conversion rule; never fabricate a single date."""
    text = " ".join(raw.strip().split())
    quarter = re.fullmatch(r"Q([1-4])\s+(20\d{2})", text, re.I)
    if quarter:
        q, year = int(quarter.group(1)), int(quarter.group(2))
        start_month = 1 + (q - 1) * 3
        end_month = start_month + 2
        return date(year, start_month, 1), date(year, end_month, monthrange(year, end_month)[1]), "calendar_quarter_range"
    half = re.fullmatch(r"H([12])\s+(20\d{2})", text, re.I)
    if half:
        h, year = int(half.group(1)), int(half.group(2))
        return (date(year, 1, 1), date(year, 6, 30), "calendar_half_range") if h == 1 else (date(year, 7, 1), date(year, 12, 31), "calendar_half_range")
    year = re.fullmatch(r"CY\s*(20\d{2})", text, re.I)
    if year:
        y = int(year.group(1))
        return date(y, 1, 1), date(y, 12, 31), "calendar_year_range"
    return None, None, None


def source_excerpt(text: str, start: int, end: int, padding: int = 100) -> str:
    left = max(0, start - padding)
    right = min(len(text), end + padding)
    return " ".join(text[left:right].split())
