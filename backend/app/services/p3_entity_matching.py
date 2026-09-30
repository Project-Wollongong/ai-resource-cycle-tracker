"""Conservative P01 entity matching for P03 source text.

Only approved current identities are eligible.  Matching uses complete token
boundaries; short names such as ``Yin`` must never match ``assaying``.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from .stock_identity import normalize


def contains_identity(text: str, identity: str) -> bool:
    haystack = normalize(text)
    needle = normalize(identity)
    if not haystack or not needle:
        return False
    words = [re.escape(part) for part in needle.split()]
    pattern = r"(?<![0-9a-z])" + r"\s+".join(words) + r"(?![0-9a-z])"
    return re.search(pattern, haystack) is not None


def unique_identity_match(text: str, rows: Iterable, id_attribute: str):
    matches: dict[int, object] = {}
    for row in rows:
        if contains_identity(text, row.value):
            matches[getattr(row, id_attribute)] = row
    return next(iter(matches.values())) if len(matches) == 1 else None
