"""Column-aligned reading of JORC resource / reserve tables.

A JORC table gives every element of a deposit its own column:

    Tonnes CuEq Cu  Au    Ag    Mo  Copper Eq Copper Gold Silver Molybdenum
    (Mt)   (%)  (%) (g/t) (g/t) (ppm) (kt)    (kt)   (koz) (koz)  (kt)
    Probable 356 0.42 0.34 0.07 0.37 98 1,482 1,213 844 4,248 35

Reading the first three numbers after the classification and calling them
tonnage / gold grade / gold ounces happens to work for a single-commodity gold
table and is badly wrong for everything else — it turned a tantalum ppm figure
into gold ounces for one lithium producer, and the result looked entirely
plausible downstream. So the units are read from the header and the values are
matched to them by position, and when the two do not line up nothing is emitted:
a missing fact is recoverable, a confidently wrong one is not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# element label -> the commodity it reports
COMMODITY_BY_LABEL = {
    "au": "gold", "gold": "gold",
    "cu": "copper", "copper": "copper",
    "ag": "silver", "silver": "silver",
    "mo": "molybdenum", "molybdenum": "molybdenum",
    "li2o": "lithium", "lithium": "lithium", "li": "lithium",
    "ta2o5": "tantalum", "tantalum": "tantalum",
    "fe2o3": "iron", "fe": "iron", "iron": "iron",
    "u3o8": "uranium", "uranium": "uranium",
    "treo": "rare_earth", "ree": "rare_earth",
    "ni": "nickel", "nickel": "nickel",
    "zn": "zinc", "zinc": "zinc",
    "pb": "lead", "lead": "lead",
    "co": "cobalt", "cobalt": "cobalt",
}
# "copper equivalent" rolls several metals into one number; it is a derived
# figure, never the primary commodity of the table
EQUIVALENT_MARKERS = ("eq", "equivalent")

GRADE_UNITS = {"%", "g/t", "ppm", "ppb", "oz/t"}
TONNAGE_UNITS = {"mt", "kt", "t", "tonnes", "mlb"}
CONTAINED_UNITS = {"kt", "koz", "moz", "oz", "t", "mlb", "klb"}

CLASSIFICATIONS = ("Measured", "Indicated", "Inferred", "Proved", "Proven", "Probable", "Total")
_UNIT_TOKEN = re.compile(r"\(([^)]{1,18})\)")
# must start and end on a digit: a lone "," or "-" in an empty table cell is
# not a number, and stripping its separators would leave an empty string
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Column:
    unit: str          # normalised unit text, e.g. "g/t", "%", "koz"
    label: str | None  # element label from the header, e.g. "Au", "Li2O"
    commodity: str | None
    is_equivalent: bool


@dataclass(frozen=True)
class ResourceRow:
    classification: str
    columns: list[Column]
    values: list[float]
    tonnage_mt: float | None
    grade: tuple[float, str, str] | None          # value, unit, commodity
    contained: tuple[float, str, str] | None      # value, unit, commodity
    commodity: str | None
    start: int
    end: int


def _normalise_unit(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip().lower()


def _unit_kind(unit: str) -> str:
    base = unit.split()[0] if unit else ""
    if base in GRADE_UNITS:
        return "grade"
    if base in TONNAGE_UNITS or unit in TONNAGE_UNITS:
        return "mass"
    return "other"


def _element_in_unit(unit_raw: str) -> str | None:
    """`(g/t Au)` carries its element inside the unit token itself."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]*", unit_raw)
    for token in reversed(tokens):
        if token.casefold() in COMMODITY_BY_LABEL:
            return token
    return None


def _commodity_for(label: str | None) -> tuple[str | None, bool]:
    """An equivalent grade (CuEq, AuEq) is derived from several metals, so it
    is flagged and never chosen as the table's primary commodity."""
    if not label:
        return None, False
    lowered = label.strip().casefold()
    is_equivalent = any(marker in lowered for marker in EQUIVALENT_MARKERS)
    key = re.sub(r"\s*(eq|equivalent)\s*$", "", lowered).strip()
    return COMMODITY_BY_LABEL.get(key), is_equivalent


def _unit_line_columns(lines: list[str]) -> list[Column] | None:
    """Layout A — a row of units under a row of element labels:

        Tonnes CuEq Cu  Au    ...
        (Mt)   (%)  (%) (g/t) ...

    The two rows correspond by position, not by adjacency, so pair them by
    index and only when the counts agree.
    """
    for index in range(len(lines) - 1, -1, -1):
        units = _UNIT_TOKEN.findall(lines[index])
        if len(units) < 3:
            continue
        stripped = _UNIT_TOKEN.sub("", lines[index]).strip()
        if len(stripped) > len(lines[index]) * 0.4:
            continue  # too much prose to be a unit row
        labels: list[str] = []
        for previous in range(index - 1, max(index - 3, -1), -1):
            candidate = re.findall(r"[A-Za-z][A-Za-z0-9]*(?:\s+Eq)?", lines[previous])
            if len(candidate) == len(units):
                labels = candidate
                break
        columns: list[Column] = []
        for position, unit_raw in enumerate(units):
            unit = _normalise_unit(unit_raw)
            label = _element_in_unit(unit_raw) or (labels[position] if labels else None)
            commodity, is_equivalent = _commodity_for(label)
            columns.append(Column(unit=unit, label=label, commodity=commodity, is_equivalent=is_equivalent))
        return columns
    return None


def _adjacent_columns(header_text: str) -> list[Column]:
    """Layout B — each unit on its own line under its own label:

        Li2O
        (%)
        Ta2O5
        (ppm)
    """
    columns: list[Column] = []
    for match in _UNIT_TOKEN.finditer(header_text):
        unit_raw = match.group(1)
        unit = _normalise_unit(unit_raw)
        if not unit or unit.isdigit():
            continue
        label = _element_in_unit(unit_raw)
        if label is None:
            preceding = header_text[: match.start()]
            tokens = re.findall(r"[A-Za-z][A-Za-z0-9]*(?:\s+Eq)?", preceding)
            label = tokens[-1].strip() if tokens else None
        commodity, is_equivalent = _commodity_for(label)
        columns.append(Column(unit=unit, label=label, commodity=commodity, is_equivalent=is_equivalent))
    return columns


def parse_header_columns(header_text: str) -> list[Column]:
    """Ordered columns read from the unit row of a resource table."""
    lines = header_text.splitlines()[-14:]
    aligned = _unit_line_columns(lines)
    if aligned:
        return aligned
    return _adjacent_columns(header_text)


def _pick_primary(columns: list[Column], values: list[float]) -> tuple[int | None, int | None, str | None]:
    """Grade and contained-metal columns for the table's primary commodity.

    The primary commodity is the one reported both as a grade and as a contained
    quantity; equivalents are excluded because they are derived from the others.
    """
    grades: dict[str, int] = {}
    contained: dict[str, int] = {}
    for index, column in enumerate(columns):
        if column.is_equivalent or not column.commodity:
            continue
        kind = _unit_kind(column.unit)
        base = column.unit.split()[0] if column.unit else ""
        if kind == "grade" and column.commodity not in grades:
            grades[column.commodity] = index
        elif base in CONTAINED_UNITS and column.commodity not in contained:
            contained[column.commodity] = index

    for commodity, grade_index in grades.items():
        if commodity in contained:
            return grade_index, contained[commodity], commodity
    if len(grades) == 1:
        commodity, grade_index = next(iter(grades.items()))
        # a single-commodity table often leaves the contained column unlabelled
        # ("Ounces (Koz)"); with only one grade on the table it can only be that
        # commodity, so adopt it rather than dropping the row
        for index, column in enumerate(columns):
            base = column.unit.split()[0] if column.unit else ""
            if index != grade_index and base in CONTAINED_UNITS and not column.commodity:
                return grade_index, index, commodity
        return grade_index, None, commodity
    return None, None, None


def _tonnage_index(columns: list[Column]) -> int | None:
    for index, column in enumerate(columns):
        base = column.unit.split()[0] if column.unit else ""
        if base in {"mt", "t", "tonnes"} and not column.commodity:
            return index
    for index, column in enumerate(columns):
        if (column.unit.split()[0] if column.unit else "") == "mt":
            return index
    return None


def parse_resource_rows(text: str) -> list[ResourceRow]:
    """Every classification row whose value count matches the header columns."""
    rows: list[ResourceRow] = []
    for match in re.finditer(
        rf"^\s*({'|'.join(CLASSIFICATIONS)})\b([^\n]*)$", text, re.I | re.M
    ):
        classification, remainder = match.group(1), match.group(2)
        values = []
        for token in _NUMBER.findall(remainder):
            cleaned = token.replace(",", "")
            try:
                values.append(float(cleaned))
            except ValueError:
                # a malformed cell makes the whole row's column alignment
                # unreliable, so drop the row rather than shift every value
                values = []
                break
        if not values:
            continue
        columns = parse_header_columns(text[: match.start()])
        # the header may describe more columns than this row fills; only the
        # trailing block that matches the row's width can be aligned safely
        if len(columns) < len(values):
            continue
        columns = columns[len(columns) - len(values):]

        tonnage_index = _tonnage_index(columns)
        grade_index, contained_index, commodity = _pick_primary(columns, values)
        rows.append(
            ResourceRow(
                classification=classification.title(),
                columns=columns,
                values=values,
                tonnage_mt=values[tonnage_index] if tonnage_index is not None else None,
                grade=(
                    (values[grade_index], columns[grade_index].unit, commodity)
                    if grade_index is not None and commodity
                    else None
                ),
                contained=(
                    (values[contained_index], columns[contained_index].unit, commodity)
                    if contained_index is not None and commodity
                    else None
                ),
                commodity=commodity,
                start=match.start(),
                end=match.end(),
            )
        )
    return rows
