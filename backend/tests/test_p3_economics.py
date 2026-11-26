"""Project economics extraction: what it must find, and what it must not."""
from app.services.p3_economics import extract_economics


def one(text, fact_type):
    return next((e for e in extract_economics(text) if e["fact_type"] == fact_type), None)


# --- recall: the term is usually not the acronym ----------------------------

def test_a_capital_estimate_written_out_is_found():
    """Seventy-two filings discuss a capital estimate; matching only "CAPEX"
    found two of them."""
    found = one("initial capital expenditure of A$277 million (including contingency)", "capex")

    assert found["numeric"] == 277_000_000
    assert found["currency"] == "A$"


def test_an_all_in_sustaining_cost_written_out_is_found():
    found = one("produced 715koz of gold at an all-in sustaining cost of $1,717/oz", "aisc")

    assert found["numeric"] == 1717
    assert found["unit"] == "/oz"


def test_an_npv_with_the_rate_glued_to_the_term_is_found():
    """"NPV7%" has no word boundary after NPV, so \\bNPV\\b never matched it."""
    found = one("base case post-tax NPV7% of $322 million, an IRR of 281%", "npv")

    assert found["numeric"] == 322_000_000
    assert found["discount_rate_pct"] == 7.0
    assert found["tax_basis"] == "post-tax"


def test_a_trailing_discount_rate_is_picked_up():
    found = one("an after-tax NPV of A$1.52 billion at a 6.5% discount rate", "npv")

    assert found["numeric"] == 1_520_000_000
    assert found["discount_rate_pct"] == 6.5
    assert found["complete"] is True


def test_an_npv_without_a_discount_rate_is_marked_incomplete():
    """A$1.5bn at 6.5% and A$1.5bn at 10% describe different projects, so a
    rate-less figure is reported as unusable rather than as a number."""
    found = one("the project NPV is A$1.5 billion", "npv")

    assert found["numeric"] == 1_500_000_000
    assert found["complete"] is False
    assert found["discount_rate_pct"] is None


# --- precision: the acronym is often not the term ---------------------------

def test_irregular_and_irrigation_are_not_internal_rates_of_return():
    """"irr" occurs 215 times across the stored filings; 84 are the term."""
    assert one("extensive irregular breccia zones between the two shears", "irr") is None
    assert one("licensing under the Rights in Water and Irrigation Act 1914", "irr") is None


def test_a_glossary_line_yields_no_figure():
    assert one("NPV Net present value NSW New South Wales October 2026", "npv") is None


def test_a_risk_policy_paragraph_does_not_donate_its_standard_number():
    text = ("reputational, compliance, financial and project value (NPV). The Company's "
            "risk management processes are aligned with ISO 31000:2018")

    assert one(text, "npv") is None


def test_a_year_is_not_a_capital_estimate():
    assert one("capital expenditure commencing in 2029", "capex") is None


def test_a_sensitivity_step_is_not_a_capital_estimate():
    assert one("capital expenditure • A relative change of +/- 10", "capex") is None


def test_a_scaling_factor_is_not_a_project_npv():
    """A currency mark alone does not separate a project valuation from a
    per-share conversion sitting beside the same word."""
    assert one("NPV (Scaled @ $4.30 per share)", "npv") is None


def test_a_figure_far_from_its_term_is_not_claimed():
    text = "NPV" + " and various other considerations apply throughout, " * 3 + "A$900 million"

    assert one(text, "npv") is None


# --- attribution ------------------------------------------------------------

def test_a_produced_cost_is_marked_as_an_actual_result():
    """A cost the company reported producing at and a study's forecast of one
    are different claims about the world."""
    found = one("We produced 715koz of gold at an all-in sustaining cost of $1,717/oz", "aisc")

    assert found["basis"] == "actual_result"


def test_a_study_figure_is_marked_as_an_estimate():
    found = one("the DFS returned an after-tax NPV of A$1.52 billion at a 6.5% discount rate",
                "npv")

    assert found["basis"] == "study_estimate"


def test_an_independent_expert_figure_is_marked_as_third_party():
    found = one("the independent expert assumed pre-production capital expenditure "
                "of $29.34 million", "capex")

    assert found["basis"] == "third_party"


def test_an_unattributed_figure_says_unknown_rather_than_assuming_a_study():
    found = one("Capital cost: A$120 million", "capex")

    assert found["basis"] == "unknown"


# --- shape ------------------------------------------------------------------

def test_an_amount_carries_the_currency_not_the_scale_word_as_its_unit():
    found = one("initial capital expenditure of $333.4 million", "capex")

    assert found["numeric"] == 333_400_000
    assert found["unit"] == "$"
    assert found["scale_word"] == "million"


def test_payback_keeps_its_period_unit():
    months = one("payback period of approximately 13 months", "payback")
    years = one("payback period of approximately 1.7 years", "payback")

    assert (months["numeric"], months["unit"]) == (13.0, "months")
    assert (years["numeric"], years["unit"]) == (1.7, "years")


def test_a_figure_past_a_sentence_end_belongs_to_the_next_sentence():
    """HAS's filing reads "IRR . Wyloo has commenced a formal sale process at
    60%" — the 60% is the sale's, not the project's."""
    text = "post-tax IRR . Wyloo has commenced a formal sale process covering 60% of it"

    assert one(text, "irr") is None


def test_a_decimal_point_is_not_a_sentence_end():
    found = one("an after-tax NPV of A$1.52 billion at a 6.5% discount rate", "npv")

    assert found["numeric"] == 1_520_000_000


def test_a_subscript_discount_rate_is_read():
    """One filer writes the rate as a subscript: "NPV ₈ of US$6.0 billion"."""
    found = one("NPV ₈ of US$6.0 billion", "npv")

    assert found["numeric"] == 6_000_000_000
    assert found["discount_rate_pct"] == 8.0
