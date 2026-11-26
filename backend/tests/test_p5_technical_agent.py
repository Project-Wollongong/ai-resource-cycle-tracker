"""The Technical Agent: what it writes, what it refuses to write, and why."""
import ast
import json
from pathlib import Path

from app.models import AnalyticalSignal, Stock
from app.services.p5_technical_agent import ENGINE, LOGIC_VERSION, analyse, build_narrative
from tests.test_technical_lenses import bars, flat, rising


def _stock(db_session, code="TEC"):
    stock = Stock(code=code, name=f"{code} Ltd", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    return stock


def _written(db_session):
    return db_session.query(AnalyticalSignal).filter_by(engine=ENGINE).all()


def test_a_quiet_stock_produces_no_signal_at_all(db_session):
    """The PRD allows No Material Signal and forbids manufacturing one."""
    stock = _stock(db_session)

    analyse(db_session, stock.id, bars(flat(260)))
    db_session.commit()

    assert _written(db_session) == []


def test_a_stock_in_a_clean_advance_produces_several_lenses(db_session):
    stock = _stock(db_session)

    analyse(db_session, stock.id, bars(rising(260)))
    db_session.commit()

    lenses = {json.loads(row.metadata_json)["lens"] for row in _written(db_session)}
    assert "trend" in lenses
    assert "structure" in lenses


def test_the_seven_lenses_share_one_dependency_group(db_session):
    """They read the same price series, so a day of agreeing lenses is one
    source. Separate groups would let the fusion layer count it as seven
    independent confirmations of the same thing."""
    stock = _stock(db_session)

    analyse(db_session, stock.id, bars(rising(260)))
    db_session.commit()

    groups = {row.dependency_group for row in _written(db_session)}
    assert len(groups) == 1
    assert groups.pop().startswith("price_action:")


def test_running_twice_updates_rather_than_duplicates(db_session):
    stock = _stock(db_session)
    price = bars(rising(260))

    analyse(db_session, stock.id, price)
    db_session.commit()
    first = len(_written(db_session))
    analyse(db_session, stock.id, price)
    db_session.commit()

    assert len(_written(db_session)) == first


def test_every_signal_carries_the_narrative_and_the_prd_enums(db_session):
    stock = _stock(db_session)

    analyse(db_session, stock.id, bars(rising(260)))
    db_session.commit()

    for row in _written(db_session):
        metadata = json.loads(row.metadata_json)
        assert row.narrative and "技术面七视角" in row.narrative
        assert metadata["magnitude_label"] in {"minor", "moderate", "strong", "exceptional"}
        assert metadata["confidence_label"] in {"low", "medium", "high"}
        assert row.persistence in {"short", "medium", "long", "structural"}
        assert row.logic_version == LOGIC_VERSION
        assert 0 < row.magnitude <= 1.0


def test_the_narrative_names_every_lens_including_the_silent_ones(db_session):
    """Seven lenses were examined whether or not seven had something to say;
    omitting the quiet ones would hide how much was actually checked."""
    narrative = build_narrative(
        __import__("app.analysis.technical_lenses", fromlist=["read_all"]).read_all(
            bars(flat(260))
        ),
        bars(flat(260))[-1].date,
    )

    for lens in ("trend", "momentum", "participation", "volatility", "structure",
                 "breakout", "exhaustion"):
        assert lens in narrative
    assert "本日不产生技术信号" in narrative


def test_the_narrative_says_so_when_the_lenses_disagree(db_session):
    """An advance that has run too far reads bullish on trend and bearish on
    exhaustion. Reporting only the count of positives would lose that."""
    stock = _stock(db_session)
    # a long quiet base, then a near-vertical run: stacked averages, stretched price
    analyse(db_session, stock.id, bars(flat(240) + [1.0 + 0.08 * i for i in range(1, 15)]))
    db_session.commit()

    narratives = {row.narrative for row in _written(db_session)}
    assert len(narratives) == 1
    assert "内部存在分歧" in narratives.pop()


def test_the_agent_never_reaches_another_engine():
    """Isolation has to hold at the service layer too, not only in the lenses."""
    imported = _imported_modules("app/services/p5_technical_agent.py")

    for forbidden in ("announcement", "scoring", "fusion", "adapter",
                      "fundamental", "catalyst", "attention", "trade"):
        offenders = [name for name in imported if forbidden in name.lower()]
        assert not offenders, f"the technical agent must not import {offenders}"
    # it may name AnalyticalSignal, and nothing else out of the model layer
    model_imports = {name for name in imported if name.startswith("..models.")}
    assert model_imports == {"..models.AnalyticalSignal"}


def _imported_modules(relative_path: str) -> set[str]:
    """Every module name this file pulls in, from the syntax tree rather than
    the text — a module named in a sentence of prose is not a dependency."""
    source = Path(__file__).resolve().parents[1] / relative_path
    tree = ast.parse(source.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # keep the leading dots: "..models" is a different reach than "models"
            base = "." * node.level + (node.module or "")
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names

