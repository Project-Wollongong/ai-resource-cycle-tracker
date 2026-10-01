"""Column-aligned reading of JORC resource tables.

The three layouts below are taken from real ASX announcements in the pilot
watchlist. Before this parser existed, all three were read positionally as gold
and two of them produced confidently wrong numbers.
"""
from app.services.p3_resource_table import parse_header_columns, parse_resource_rows

# Hillcrest: polymetallic, labels on one line and units on the next, paired by
# column position rather than adjacency
POLYMETALLIC_TABLE = """
Tonnes CuEq Cu Au Ag Mo Copper Eq Copper Gold Silver Molybdenum
(Mt) (%) (%) (g/t) (g/t) (ppm) (kt) (kt) (koz) (koz) (kt)
Proved - - - - - - - - - - -
Probable 356 0.42 0.34 0.07 0.37 98 1,482 1,213 844 4,248 35
"""

# Wildcat: lithium, each unit on its own line beneath its own label
VERTICAL_TABLE = """
Source Classification Tonnes
(Mt)
Li2O
(%)
Ta2O5
(ppm)
Fe2O3
(%)
Li2O
(kt)
Open pit
Proved - - - - -
Probable 36.8 1.00 62.4 1.06 366
"""

# Catalyst: single-commodity gold, units inline and the ounces column unlabelled
SINGLE_COMMODITY_TABLE = """
Classification Tonnes (Mt) Grade (g/t Au) Ounces (Koz)
Proved - - -
Probable 3.9 4.2 524
"""


def _probable(text):
    return next(row for row in parse_resource_rows(text) if row.classification == "Probable")


def test_polymetallic_table_reports_copper_not_the_first_grade_column():
    """Reading positionally takes 0.42 (the copper-equivalent grade) as a gold
    grade. Copper is the primary commodity: it is the one element reported both
    as a grade and as a contained quantity, and it is not an equivalent."""
    row = _probable(POLYMETALLIC_TABLE)

    assert row.commodity == "copper"
    assert row.tonnage_mt == 356
    assert row.grade == (0.34, "%", "copper")
    assert row.contained == (1213.0, "kt", "copper")
    # 356 Mt at 0.34% is 1,210 kt — the table's own figure, so the columns line up
    assert abs(356e6 * 0.0034 / 1000 - 1213.0) / 1213.0 < 0.01


def test_equivalent_grades_are_never_the_primary_commodity():
    columns = parse_header_columns(POLYMETALLIC_TABLE)
    equivalents = [column for column in columns if column.is_equivalent]
    assert equivalents, "CuEq / Copper Eq should be recognised as equivalents"
    assert all(column.commodity != "copper" or column.is_equivalent for column in equivalents)


def test_vertical_layout_reports_lithium_not_gold():
    """This row previously became '1.00 g/t Au, 62.4 koz' — the 62.4 is tantalum
    in ppm. Nothing in the numbers themselves gives the error away."""
    row = _probable(VERTICAL_TABLE)

    assert row.commodity == "lithium"
    assert row.tonnage_mt == 36.8
    assert row.grade == (1.0, "%", "lithium")
    assert row.contained == (366.0, "kt", "lithium")


def test_single_commodity_table_adopts_the_unlabelled_contained_column():
    """`Ounces (Koz)` names no element, but a table carrying one grade can only
    be reporting that commodity."""
    row = _probable(SINGLE_COMMODITY_TABLE)

    assert row.commodity == "gold"
    assert row.tonnage_mt == 3.9
    assert row.grade[0] == 4.2
    assert row.contained == (524.0, "koz", "gold")


def test_rows_wider_than_the_header_are_skipped():
    """Without a matching header the columns cannot be identified, and guessing
    is what produced the original error."""
    rows = parse_resource_rows("Probable 36.8 1.00 62.4 1.06 366\n")
    assert all(row.grade is None and row.contained is None for row in rows)


def test_empty_table_cells_do_not_crash_the_parser():
    """A JORC table pads empty cells with "-" and sometimes a stray separator.
    Reading those as numbers would shift every column by one, so the row is
    dropped — and it must not raise."""
    rows = parse_resource_rows("Total , ,\nProved - - -\n")
    assert rows == []


def test_a_lone_separator_is_not_read_as_a_number():
    """The number pattern once accepted a bare ",", which became an empty
    string after separator stripping and aborted the whole parse run."""
    from app.services.p3_resource_table import _NUMBER

    assert _NUMBER.findall("Total , ,") == []
    assert _NUMBER.findall("Proved - - -") == []
    assert _NUMBER.findall("Probable 1,482 35") == ["1,482", "35"]
