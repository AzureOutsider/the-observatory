from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

DATABASE_URL = settings.database_url
DB_PATH = Path(DATABASE_URL.removeprefix("sqlite:///")) if DATABASE_URL.startswith("sqlite:///") else None
DATA_DIR = DB_PATH.parent if DB_PATH else Path(__file__).resolve().parents[1] / "data"


class Base(DeclarativeBase):
    pass


def make_engine(url: str = DATABASE_URL):
    if url.startswith("sqlite:///"):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
    return create_engine(url, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Keep existing SQLite installations usable when new nullable fields are added.
    migrations = {
        "assets": {"custom_name": "VARCHAR(255)"},
        "watchlist_items": {"tags_json": "TEXT"},
        "holdings": {
            "last_valuation_at": "DATETIME",
            "last_valuation_source": "VARCHAR(80)",
            "last_manual_adjustment_at": "DATETIME",
            "last_manual_adjustment_reason": "TEXT",
            "last_update_type": "VARCHAR(32)",
        },
        "transactions": {
            "retracted_at": "DATETIME",
            "retraction_reason": "TEXT",
            "retraction_effect": "TEXT",
        },
        "news_items": {
            "summary": "TEXT",
            "fetched_at": "DATETIME",
            "importance": "INTEGER",
            "tags_json": "TEXT",
            "content_hash": "VARCHAR(64)",
            "quality": "VARCHAR(32)",
        },
    }
    with engine.begin() as connection:
        for table, columns in migrations.items():
            existing = {column["name"] for column in inspect(engine).get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_price_snapshots_asset_source_observed_at "
                "ON price_snapshots (asset_id, source, observed_at)"
            )
        )
        # Enforce news dedupe at the storage layer. Existing duplicates must be
        # cleaned before this runs; the cleanup script keeps the latest id per
        # content_hash so the unique index can be created cleanly.
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_news_items_content_hash "
                "ON news_items (content_hash)"
            )
        )


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
