from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Stock
from app.services import stock_identity as identity


def make_stock(db, code="CVV", name="Company Vision"):
    stock = Stock(code=code, name=name, commodity="GOLD", active=True)
    db.add(stock)
    db.flush()
    identity.ensure_current_identities(db, stock, source="test")
    return stock


def test_historical_ticker_and_name_resolve_to_same_stock(db_session):
    stock = make_stock(db_session)
    identity.add_history(
        db_session,
        stock,
        kind="ticker",
        value="OLD",
        valid_from=date(2018, 1, 1),
        valid_to=date(2022, 1, 1),
    )
    identity.add_history(
        db_session,
        stock,
        kind="company_name",
        value="Old Company",
        valid_from=date(2018, 1, 1),
        valid_to=date(2022, 1, 1),
    )
    assert identity.resolve_stock(db_session, "OLD", date(2020, 6, 1)).id == stock.id
    assert identity.resolve_stock(db_session, "old company", date(2020, 6, 1)).id == stock.id
    assert identity.resolve_stock(db_session, "OLD", date(2023, 1, 1)) is None


def test_identity_change_closes_old_rows_and_updates_current_code(db_session):
    stock = make_stock(db_session)
    identity.change_current_identity(
        db_session,
        stock,
        code="NEW",
        name="New Company",
        effective_from=date(2024, 1, 1),
    )
    assert stock.code == "NEW"
    assert identity.resolve_stock(db_session, "CVV", date(2023, 12, 31)).id == stock.id
    assert identity.resolve_stock(db_session, "CVV", date(2024, 1, 1)) is None
    assert identity.resolve_stock(db_session, "NEW") .id == stock.id


def test_duplicate_historical_identity_is_rejected(db_session):
    first = make_stock(db_session, "AAA", "First")
    second = make_stock(db_session, "BBB", "Second")
    identity.add_history(
        db_session,
        first,
        kind="ticker",
        value="FORMER",
        valid_from=date(2019, 1, 1),
        valid_to=date(2020, 1, 1),
    )
    with pytest.raises(identity.IdentityConflict):
        identity.add_history(
            db_session,
            second,
            kind="ticker",
            value="FORMER",
            valid_from=date(2019, 6, 1),
            valid_to=date(2020, 6, 1),
        )


def test_identity_row_constraints_are_enforced(db_session):
    stock = make_stock(db_session)
    with pytest.raises((ValueError, IntegrityError)):
        identity.add_history(db_session, stock, kind="ticker", value="BAD", valid_from=date(2025, 1, 1), valid_to=date(2024, 1, 1))
