"""Project economics figures, read out of study announcements.

Three things make this harder than matching a term and a number.

The term is often not the acronym. A capital estimate is as likely to read
"initial capital expenditure of A$277 million" as "CAPEX", and an all-in
sustaining cost is usually spelled out. Matching only the acronym found two
capital estimates in seventy-two documents that discuss one.

The acronym is often not the term. "irr" appears 215 times across the stored
filings and is the internal rate of return in 84 of them; the rest are inside
"irregular" and "Irrigation Act". Word boundaries settle that, but not the
next problem: a glossary line reading "NPV Net present value NSW New South
Wales" is a definition, and a risk-policy paragraph mentioning project value
is neither a definition nor a figure. Both are excluded by requiring the
number to sit close to the term rather than merely somewhere after it.

And an NPV without its discount rate is not a number anyone can use. A$1.5bn
at 6.5% and A$1.5bn at 10% describe different projects. Where the rate cannot
be read, the figure is recorded as incomplete rather than quietly reported.
"""

from __future__ import annotations

import re
from typing import Iterable

# Everything must sit within this many characters of its term. The cheapest
# defence against a glossary or a policy paragraph donating an unrelated digit.
_WINDOW = 70

_MONEY = r"(?P<currency>A?\$|US\s?\$)?\s*(?P<value>[\d,]+(?:\.\d+)?)\s*(?P<scale>billion|million|bn\b|m\b)?"
_PER_UNIT = r"(?P<currency>A?\$|US\s?\$)?\s*(?P<value>[\d,]+(?:\.\d+)?)\s*(?P<unit>/\s*(?:oz|t|lb|tonne)|per\s+(?:ounce|tonne|pound))"

# term -> (fact_type, label, value pattern, quantity type)
_TERMS: tuple[tuple[str, str, str, str, str], ...] = (
    (r"(?:\bNPV\b|\bNPV(?=\d)|net present value)", "npv", "NPV", _MONEY, "amount"),
    (r"(?:\bIRR\b|internal rate of return)", "irr", "IRR",
     r"(?P<value>\d+(?:\.\d+)?)\s*%", "percentage"),
    (r"\bpayback(?:\s+period)?\b", "payback", "Payback",
     r"(?:of\s+)?(?:approximately\s+)?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>years?|months?)", "duration"),
    (r"(?:\bCAPEX\b|capital expenditure|capital cost|pre-?production capital|initial capital)",
     "capex", "CAPEX", _MONEY, "amount"),
    (r"(?:\bOPEX\b|operating cost)", "opex", "OPEX", _PER_UNIT, "amount"),
    (r"(?:\bAISC\b|all[- ]in sustaining cost)", "aisc", "AISC", _PER_UNIT, "amount"),
)

_SCALE = {"billion": 1_000_000_000, "bn": 1_000_000_000,
          "million": 1_000_000, "m": 1_000_000}

# Project-level money. Anything smaller is a share price, a unit cost or a
# scaling factor that happened to sit next to the term.
_PROJECT_SCALE_FLOOR = 1_000_000

# What the figure is a figure *of*. A produced-and-reported cost and a study's
# forecast of one are different claims; so is a third party's valuation of the
# company. Where no cue is present the basis stays unknown rather than being
# assumed to be the study.
_BASIS_CUES = (
    ("actual_result", r"\b(?:we |the group |the company )?produced\b|\bactual\b|\bguidance\b|\bFY\d{2}\b"),
    ("third_party", r"independent expert|we consider|the Scheme|valuation range"),
    ("study_estimate", r"\bstudy\b|\bDFS\b|\bPFS\b|scoping|base case|\bestimated?\b|feasibility"),
)

_TAX_BASIS = r"(post[- ]tax|after[- ]tax|pre[- ]tax|before tax)"
_DISCOUNT = r"(?:at\s+(?:a\s+)?)?(\d+(?:\.\d+)?)\s*%\s*(?:discount|nominal|real)"


_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def _same_sentence(window: str) -> str:
    """The window up to the first sentence end.

    HAS's filing reads "IRR . Wyloo has commenced a formal sale process", and
    a figure further down that sentence belongs to the sale, not to the IRR.
    A decimal point inside a number is not a sentence end, so the break has to
    be punctuation followed by space. A colon is not a break either: it is
    usually what introduces the figure, as in "Capital cost: A$120 million".
    """
    return re.split(r"(?<=[.;])\s|\n", window, maxsplit=1)[0]


def _scale_of(token: str | None) -> int:
    return _SCALE.get((token or "").strip().lower(), 1)


def _basis(context: str) -> str:
    for name, pattern in _BASIS_CUES:
        if re.search(pattern, context, re.I):
            return name
    return "unknown"


def _npv_qualifiers(term_start: int, text: str) -> dict:
    """An NPV's discount rate and tax basis, from the text around it.

    The rate is written either glued to the term ("NPV7%", "NPV8") or trailing
    it ("at a 6.5% discount rate"), so both are tried before giving up.
    """
    # "NPV ₈" is how one filer writes the rate; normalising the subscripts
    # costs nothing and the alternative is losing the rate entirely
    around = text[max(0, term_start - 60): term_start + 160].translate(_SUBSCRIPTS)
    head = text[term_start: term_start + 12].translate(_SUBSCRIPTS)
    glued = re.search(r"NPV\s*(\d+(?:\.\d+)?)\s*%?", head, re.I)
    trailing = re.search(_DISCOUNT, around, re.I)
    rate = glued.group(1) if glued else (trailing.group(1) if trailing else None)
    tax = re.search(_TAX_BASIS, around, re.I)
    return {
        "discount_rate_pct": float(rate) if rate else None,
        "tax_basis": tax.group(1).lower().replace(" ", "-") if tax else None,
        # the figure is unusable for comparison without the rate, and saying so
        # is more useful than publishing a bare number
        "complete": rate is not None,
    }


def extract_economics(text: str) -> list[dict]:
    """Every project-economics figure in one page of text.

    Returns dicts, not fact candidates: the caller owns the fact contract.
    """
    found: list[dict] = []
    for term_pattern, fact_type, label, value_pattern, quantity_type in _TERMS:
        for term in re.finditer(term_pattern, text, re.I):
            window = _same_sentence(text[term.end(): term.end() + _WINDOW])
            # The value must follow the term closely; anything further away
            # belongs to a different sentence and usually a different subject.
            # Every candidate in the window is tried rather than only the
            # first: "NPV7% of $322 million" offers the discount rate first,
            # and stopping there would lose the figure entirely.
            entry = None
            for value in re.finditer(value_pattern, window, re.I):
                groups = value.groupdict()
                try:
                    numeric = float(groups["value"].replace(",", ""))
                except (TypeError, ValueError):
                    continue
                entry = _entry(
                    text, term, value, groups, numeric,
                    fact_type, label, quantity_type,
                )
                if entry is not None:
                    break
            if entry is None:
                continue
            if fact_type == "npv":
                entry.update(_npv_qualifiers(term.start(), text))
            found.append(entry)
    return _deduplicate(found)


def _entry(text: str, term, value, groups: dict, numeric: float,
           fact_type: str, label: str, quantity_type: str) -> dict | None:
    """One candidate figure, or None when it does not survive the guards."""
    entry = {
        "fact_type": fact_type,
        "label": label,
        "quantity_type": quantity_type,
        "raw": " ".join(text[term.start(): term.end() + value.end()].split()),
        "start": term.start(),
        "end": term.end() + value.end(),
        "currency": groups.get("currency"),
        "unit": groups.get("unit"),
        "basis": _basis(text[max(0, term.start() - 140): term.end() + 140]),
    }
    if quantity_type != "amount" or "scale" not in groups:
        entry["numeric"] = numeric
        return entry

    # A money figure must look like money. Without a currency mark or a scale
    # word, "2029" is a year, "31000" is the ISO standard a risk paragraph
    # cites, "10" is a sensitivity step and "NPV7" is the discount rate — all
    # of which this rule read as dollars until the guard was added.
    if not groups.get("currency") and not groups.get("scale"):
        return None
    scaled = numeric * _scale_of(groups.get("scale"))
    # A project's NPV or capital estimate is not a single-digit dollar figure.
    # "NPV (Scaled @ $4.30" is a per-share conversion, and the currency mark
    # alone does not tell the two apart.
    if scaled < _PROJECT_SCALE_FLOOR:
        return None
    entry["numeric"] = scaled
    # the value is already absolute, so the unit is the currency; carrying
    # "million" alongside 333,400,000 reads as a mistake
    entry["unit"] = (groups.get("currency") or "").strip() or None
    entry["scale_word"] = groups.get("scale")
    return entry


def _deduplicate(entries: Iterable[dict]) -> list[dict]:
    """One figure per term occurrence. "NPV" and "net present value" can both
    match the same sentence, and the spelled-out form usually starts earlier."""
    best: dict[tuple, dict] = {}
    for entry in entries:
        key = (entry["fact_type"], entry["numeric"], entry["end"])
        held = best.get(key)
        if held is None or entry["start"] < held["start"]:
            best[key] = entry
    return sorted(best.values(), key=lambda item: item["start"])
