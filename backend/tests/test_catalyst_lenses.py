"""The seven catalyst lenses, each shown a project history it should recognise."""
import ast
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.analysis.catalyst_lenses import (
    INSUFFICIENT_DATA,
    LENSES,
    NO_MATERIAL_CHANGE,
    REPORTED,
    ProjectEvent,
    bottleneck,
    current_stage,
    dependency,
    derisking,
    forward,
    lifecycle,
    milestone,
    read_all,
    timeline,
)

AS_OF = date(2026, 11, 27)


def event(event_type, family, status="reported", days_ago=10, tags=()):
    return ProjectEvent(
        event_type=event_type,
        event_status=status,
        family=family,
        occurred_on=AS_OF - timedelta(days=days_ago),
        reported_on=AS_OF - timedelta(days=days_ago),
        revision_tags=tuple(tags),
    )


DRILLING = event("Drilling Results / Assay Results", "F01")
MAIDEN_MRE = event("Maiden Mineral Resource", "F02")
DFS = event("Definitive Feasibility Study / DFS", "F04")


# --- stage ------------------------------------------------------------------

def test_the_stage_is_the_furthest_point_with_evidence_not_the_latest_event():
    """Miners run drilling, metallurgy and permitting side by side; the newest
    event is often not the furthest one."""
    events = [DFS, event("Drilling Results / Assay Results", "F01", days_ago=1)]

    assert current_stage(events) == "study"


def test_lifecycle_reports_a_stage_advance():
    events = [event("Drilling Results / Assay Results", "F01", days_ago=300),
              event("Maiden Mineral Resource", "F02", days_ago=5)]
    reading = lifecycle(events, AS_OF)

    assert reading.status == REPORTED
    assert reading.direction == "positive"
    assert reading.persistence == "structural"
    assert reading.evidence["previous_stage"] == "exploration"
    assert reading.evidence["stage"] == "resource_definition"


def test_lifecycle_is_quiet_when_the_stage_has_not_moved():
    events = [event("Drilling Results / Assay Results", "F01", days_ago=300), DRILLING]

    assert lifecycle(events, AS_OF).status == NO_MATERIAL_CHANGE


# --- milestone --------------------------------------------------------------

def test_milestone_reports_a_completion():
    reading = milestone([event("Drilling Completed", "F01", status="completed")], AS_OF)

    assert reading.status == REPORTED
    assert reading.direction == "positive"


def test_a_withdrawal_outranks_a_completion():
    """A commitment taken back is the more important of the two."""
    events = [event("Drilling Completed", "F01", status="completed"),
              event("Capital Raising", "F06", tags=("Withdrawal",))]
    reading = milestone(events, AS_OF)

    assert reading.direction == "negative"
    assert reading.evidence["withdrawn"] == ["Capital Raising"]


def test_a_completion_outside_the_window_is_not_reported_as_recent():
    reading = milestone([event("Drilling Completed", "F01", status="completed", days_ago=400)],
                        AS_OF)

    assert reading.status == NO_MATERIAL_CHANGE


# --- de-risking -------------------------------------------------------------

def test_derisking_reports_an_approval():
    reading = derisking([event("Environmental Approval Status", "F05")], AS_OF)

    assert reading.status == REPORTED
    assert reading.direction == "positive"
    assert reading.persistence == "long"


def test_a_proposed_raise_is_not_yet_de_risking():
    """The PRD requires completed facts and company plans to stay apart: money
    announced is not money received."""
    reading = derisking([event("Placement", "F06", status="proposed")], AS_OF)

    assert reading.status == REPORTED
    assert reading.direction == "neutral"
    assert reading.evidence["funding_proposed_only"] == ["Placement"]


def test_money_received_is_de_risking():
    reading = derisking([event("Placement", "F06", status="funds_received")], AS_OF)

    assert reading.direction == "positive"


# --- bottleneck -------------------------------------------------------------

def test_bottleneck_names_what_a_study_stage_project_still_lacks():
    reading = bottleneck([DFS], AS_OF)

    assert reading.status == REPORTED
    assert reading.direction == "negative"
    assert any("FID" in item for item in reading.evidence["unresolved"])


def test_bottleneck_clears_once_the_evidence_is_there():
    events = [DFS, event("Environmental Approval Status", "F05"),
              event("FID Target", "F04"), event("Placement", "F06")]

    assert bottleneck(events, AS_OF).status == NO_MATERIAL_CHANGE


def test_reaching_fid_without_funding_evidence_is_itself_a_bottleneck():
    """An investment decision the project has no money to act on is the
    constraint worth naming."""
    events = [DFS, event("Environmental Approval Status", "F05"), event("FID Target", "F04")]
    reading = bottleneck(events, AS_OF)

    assert reading.status == REPORTED
    assert reading.evidence["stage"] == "development_decision"
    assert any("融资" in item for item in reading.evidence["unresolved"])


def test_bottleneck_says_missing_evidence_is_not_proof_of_absence():
    """Our announcement history is shallow, so an unseen approval may simply be
    one we never fetched."""
    reading = bottleneck([DFS], AS_OF)

    assert any("未见证据不等于不存在" in risk for risk in reading.risks)


# --- timeline ---------------------------------------------------------------

def test_timeline_reports_a_revision():
    reading = timeline([event("Study Update / Revision", "F04", tags=("Revised",))], AS_OF)

    assert reading.status == REPORTED
    assert reading.direction == "negative"


def test_a_revision_does_not_claim_to_know_the_direction():
    reading = timeline([event("Study Update / Revision", "F04", tags=("Revised",))], AS_OF)

    assert any("可能是提前" in risk for risk in reading.risks)


# --- forward ----------------------------------------------------------------

def test_forward_names_the_next_event_for_the_stage():
    reading = forward([MAIDEN_MRE], AS_OF)

    assert "Scoping" in reading.evidence["next_expected_event"] or \
           "预可研" in reading.evidence["next_expected_event"]


def test_a_long_silence_is_reported_as_waiting_never_as_failure():
    """The PRD is explicit: no announcement cannot be read as a failed
    milestone."""
    reading = forward([event("Maiden Mineral Resource", "F02", days_ago=200)], AS_OF)

    assert reading.status == REPORTED
    assert reading.direction == "neutral"
    assert reading.confidence == "low"
    assert any("不能据此判定里程碑失败" in risk for risk in reading.risks)


def test_forward_never_invents_a_probability():
    reading = forward([MAIDEN_MRE], AS_OF)

    assert reading.evidence["probability"] == "not_assessed"


# --- dependency -------------------------------------------------------------

def test_dependency_reports_an_item_open_too_long():
    reading = dependency([event("Environmental Approval Status", "F05",
                                status="application", days_ago=400)], AS_OF)

    assert reading.status == REPORTED
    assert reading.evidence["stale_open_items"][0]["days_open"] == 400


def test_a_recently_opened_item_is_not_stale():
    reading = dependency([event("Environmental Approval Status", "F05",
                                status="application", days_ago=30)], AS_OF)

    assert reading.status == NO_MATERIAL_CHANGE


# --- what every lens must do ------------------------------------------------

@pytest.mark.parametrize("lens", LENSES, ids=lambda lens: lens.__name__)
def test_a_lens_with_no_events_says_so_rather_than_guessing(lens):
    reading = lens([], AS_OF)

    assert reading.status == INSUFFICIENT_DATA
    assert reading.direction == "neutral"


@pytest.mark.parametrize("lens", LENSES, ids=lambda lens: lens.__name__)
def test_every_lens_returns_the_contract_enums(lens):
    reading = lens([DRILLING, MAIDEN_MRE, DFS], AS_OF)

    assert reading.status in {REPORTED, NO_MATERIAL_CHANGE, INSUFFICIENT_DATA}
    assert reading.direction in {"positive", "negative", "neutral"}
    assert reading.magnitude in {"minor", "moderate", "strong", "exceptional"}
    assert reading.confidence in {"low", "medium", "high"}
    assert reading.persistence in {"short", "medium", "long", "structural"}
    assert reading.summary


def test_read_all_returns_all_seven_lenses():
    readings = read_all([DRILLING, MAIDEN_MRE, DFS], AS_OF)

    assert [reading.lens for reading in readings] == [
        "lifecycle", "milestone", "derisking", "bottleneck", "timeline",
        "forward", "dependency",
    ]


def test_the_catalyst_lenses_cannot_reach_price_or_another_engine():
    """The PRD forbids this agent price, volume, technical indicators and every
    other agent's conclusions. The import graph is what enforces it."""
    source = Path(__file__).resolve().parents[1] / "app/analysis/catalyst_lenses.py"
    tree = ast.parse(source.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            imported.add(base)
            imported.update(f"{base}.{alias.name}" for alias in node.names)

    for forbidden in ("indicator", "technical", "price", "bar", "fundamental",
                      "sentiment", "fusion", "scoring", "sqlalchemy", "models"):
        offenders = [name for name in imported if forbidden in name.lower()]
        assert not offenders, f"catalyst lenses must not import {offenders}"
    assert {name for name in imported if name.startswith(".")} <= {
        ".lens_reading", ".lens_reading.LensReading", ".lens_reading.REPORTED",
        ".lens_reading.NO_MATERIAL_CHANGE", ".lens_reading.INSUFFICIENT_DATA",
    }
