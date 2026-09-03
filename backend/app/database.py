from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401  (register mappings)

    Base.metadata.create_all(engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    """Keep local SQLite databases compatible with small additive schema changes."""
    with engine.begin() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(score_snapshots)")}
        if "sentiment_score" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE score_snapshots ADD COLUMN sentiment_score FLOAT NOT NULL DEFAULT 50.0"
            )
        from .models import HistoricalAnalysisSnapshot

        HistoricalAnalysisSnapshot.__table__.create(bind=conn, checkfirst=True)
        from .models import HistoricalAnalysisReturn

        HistoricalAnalysisReturn.__table__.create(bind=conn, checkfirst=True)
