"""P01 stock identity. All intervals are [valid_from, valid_to)."""
from datetime import date, datetime
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import market_tz
from ..models import Stock, StockIdentity


class IdentityConflict(ValueError):
    pass


def today() -> date:
    return datetime.now(market_tz()).date()


def clean(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalize(value: str) -> str:
    return clean(value).casefold()


def ticker(value: str) -> str:
    value = clean(value).upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,9}", value):
        raise ValueError("ticker must contain 1-10 letters, digits, dots or hyphens")
    return value


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    return (a_end is None or b_start is None or b_start < a_end) and (
        b_end is None or a_start is None or a_start < b_end
    )


def matching_rows(db: Session, value: str, kind: str | None = None, exchange: str | None = None):
    query = select(StockIdentity).where(StockIdentity.normalized_value == normalize(value))
    if kind == "ticker":
        query = query.where(StockIdentity.kind == "ticker")
    elif kind in {"company_name", "alias"}:
        query = query.where(StockIdentity.kind.in_(["company_name", "alias"]))
    if exchange:
        query = query.where((StockIdentity.exchange == clean(exchange).upper()) | StockIdentity.exchange.is_(None))
    return list(db.scalars(query))


def resolve_stock(db: Session, identifier: str, as_of: date | None = None,
                  kind: str | None = None, exchange: str | None = None) -> Stock | None:
    """Exact normalized lookup; ambiguous historical identities never guess."""
    rows = matching_rows(db, identifier, kind, exchange)
    ids = {r.stock_id for r in rows if as_of is None or (
        (r.valid_from is None or r.valid_from <= as_of) and
        (r.valid_to is None or as_of < r.valid_to))}
    # Direct ORM/seed callers may not yet have identity rows. Do not bypass the
    # effective date when a current identity IS available.
    for stock in db.scalars(select(Stock)):
        if exchange and stock.exchange != clean(exchange).upper():
            continue
        for field, row_kind in (("code", "ticker"), ("name", "company_name")):
            if kind and ((kind == "ticker") != (row_kind == "ticker")):
                continue
            if normalize(getattr(stock, field)) == normalize(identifier) and not any(
                r.kind == row_kind and r.is_current for r in stock.identity_history
            ):
                ids.add(stock.id)
    if len(ids) > 1:
        raise IdentityConflict("identity matches multiple stocks; specify kind, exchange and as_of")
    return db.get(Stock, next(iter(ids))) if ids else None


def find_current_or_historical(db: Session, identifier: str) -> Stock | None:
    # Existing stock URLs remain current-code navigation; the explicit resolver
    # is for historical evidence with a publication date.
    current = db.scalar(select(Stock).where(Stock.code == clean(identifier).upper()))
    return current if current is not None else resolve_stock(db, identifier)


def ensure_current_identities(db: Session, stock: Stock, source: str = "legacy_baseline") -> None:
    db.flush()
    for kind, value in (("ticker", stock.code), ("company_name", stock.name)):
        if not any(r.kind == kind and r.is_current for r in stock.identity_history):
            stock.identity_history.append(StockIdentity(
                kind=kind, value=value, normalized_value=normalize(value),
                exchange=stock.exchange if kind == "ticker" else None,
                is_current=True, source=source,
            ))
    db.flush()


def validate_interval(start: date | None, end: date | None) -> None:
    if start and end and start >= end:
        raise ValueError("valid_to must be after valid_from (end is exclusive)")
    if (start and start > today()) or (end and end > today()):
        raise ValueError("identity history cannot contain future effective dates")


def assert_available(db: Session, stock: Stock, kind: str, value: str,
                     exchange: str | None, start: date | None, end: date | None) -> None:
    for other in matching_rows(db, value, kind, exchange):
        if other.stock_id != stock.id and overlaps(start, end, other.valid_from, other.valid_to):
            raise IdentityConflict(f"identity overlaps stock {other.stock_id}; link to that stock instead")
    for other in db.scalars(select(Stock).where(Stock.id != stock.id)):
        if kind == "ticker" and other.exchange != exchange:
            continue
        if normalize(other.code if kind == "ticker" else other.name) != normalize(value):
            continue
        current = next((r for r in other.identity_history if r.is_current and
                        r.kind == ("ticker" if kind == "ticker" else "company_name")), None)
        if current is None or overlaps(start, end, current.valid_from, None):
            raise IdentityConflict(f"identity overlaps stock {other.id}")


def add_history(db: Session, stock: Stock, *, kind: str, value: str,
                valid_from: date | None = None, valid_to: date | None = None,
                exchange: str | None = None, source: str = "manual") -> StockIdentity:
    if kind not in {"ticker", "company_name", "alias"}:
        raise ValueError("invalid identity kind")
    validate_interval(valid_from, valid_to)
    value = ticker(value) if kind == "ticker" else clean(value)
    if not value or len(value) > 160:
        raise ValueError("identity value must contain 1-160 characters")
    exchange = clean(exchange or stock.exchange).upper() if kind == "ticker" else None
    ensure_current_identities(db, stock)
    for row in stock.identity_history:
        if row.kind == kind and row.normalized_value == normalize(value) and row.exchange == exchange:
            if not row.is_current and row.valid_from == valid_from and row.valid_to == valid_to:
                return row
            if overlaps(valid_from, valid_to, row.valid_from, row.valid_to):
                raise IdentityConflict("overlapping history for the same identity")
        if row.kind == kind and row.is_current:
            if valid_to is None:
                raise ValueError("former ticker/company name requires valid_to; use alias for an undated alternate name")
            if row.valid_from is not None and valid_to > row.valid_from:
                raise IdentityConflict("former identity extends into the known current identity period")
    assert_available(db, stock, kind, value, exchange, valid_from, valid_to)
    row = StockIdentity(kind=kind, value=value, normalized_value=normalize(value),
                        exchange=exchange, valid_from=valid_from, valid_to=valid_to,
                        is_current=False, source=clean(source))
    stock.identity_history.append(row)
    db.flush()
    return row


def change_current_identity(db: Session, stock: Stock, *, code: str | None = None,
                            name: str | None = None, exchange: str | None = None,
                            effective_from: date | None = None) -> None:
    when = effective_from or today()
    validate_interval(when, None)
    new_code = ticker(code) if code is not None else stock.code
    new_name = clean(name) if name is not None else stock.name
    new_exchange = clean(exchange).upper() if exchange is not None else stock.exchange
    if not new_name or len(new_name) > 160:
        raise ValueError("company name must contain 1-160 characters")
    ensure_current_identities(db, stock)
    changes = []
    for kind, old, new, market in (
        ("ticker", stock.code, new_code, new_exchange),
        ("company_name", stock.name, new_name, None),
    ):
        if old == new and (kind != "ticker" or new_exchange == stock.exchange):
            continue
        current = next(r for r in stock.identity_history if r.kind == kind and r.is_current)
        if current.valid_from is not None and when <= current.valid_from:
            raise ValueError("identity change must be later than the current identity start date")
        if any(r.kind == kind and not r.is_current and
               (r.valid_to is None or r.valid_to > when) for r in stock.identity_history):
            raise IdentityConflict("change date overlaps an existing historical identity")
        assert_available(db, stock, kind, new, market, when, None)
        changes.append((kind, new, market, current))
    for _, _, _, current in changes:
        current.is_current, current.valid_to = False, when
    db.flush()  # release partial unique index before inserting replacements
    for kind, new, market, _ in changes:
        stock.identity_history.append(StockIdentity(
            kind=kind, value=new, normalized_value=normalize(new), exchange=market,
            valid_from=when, is_current=True, source="api_identity_change",
        ))
    stock.code, stock.name, stock.exchange = new_code, new_name, new_exchange
    db.flush()


def assert_new_stock_identity(db: Session, code: str, name: str) -> None:
    # A reused old ticker requires explicit issuer review, not blind creation.
    for value, kind in ((code, "ticker"), (name, "company_name")):
        if resolve_stock(db, value, kind=kind) is not None:
            raise IdentityConflict("current or former identity already belongs to an existing stock")
