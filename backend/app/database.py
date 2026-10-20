"""SQLAlchemy engine, session factory, and declarative base."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _normalize(url: str) -> str:
    # Render and Heroku still emit the legacy postgres:// scheme.
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _normalize(settings.DATABASE_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Minimal forward-only migration for columns added after first deploy.

    `create_all` only creates missing *tables*, so a column added to an existing
    model is invisible to a database that was created before it. This adds any
    such column in place rather than pulling in Alembic for a handful of fields.
    Only additive, nullable/defaulted columns belong here.
    """
    from sqlalchemy import inspect, text

    # (table, column, DDL type + default)
    additions = [
        ("organizations", "plan", "VARCHAR(20) DEFAULT 'free' NOT NULL"),
        ("usage_logs", "requested_model", "VARCHAR(120)"),
        ("usage_logs", "original_tokens", "INTEGER"),
        ("usage_logs", "compressed_tokens", "INTEGER"),
        ("usage_logs", "token_reduction_pct", "FLOAT"),
        ("usage_logs", "complexity_score", "FLOAT"),
        ("usage_logs", "complexity_tier", "INTEGER"),
        ("usage_logs", "compression_savings_usd", "FLOAT"),
        ("usage_logs", "routing_savings_usd", "FLOAT"),
        ("usage_logs", "total_savings_usd", "FLOAT"),
        ("usage_logs", "techniques_applied", "VARCHAR(200)"),
        ("usage_logs", "lamport_ts", "INTEGER"),
        ("usage_logs", "origin_pod", "VARCHAR(120)"),
        ("usage_logs", "processed_by", "VARCHAR(120)"),
        ("usage_logs", "event_id", "VARCHAR(40)"),
    ]

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, ddl in additions:
            if table not in existing_tables:
                continue  # create_all will build it with the column already present
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column in columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

        # Composite indexes for cap checks, for databases created before them.
        if "usage_logs" in existing_tables:
            for name, cols in (
                ("ix_usage_user_ts", "user_id, timestamp"),
                ("ix_usage_team_ts", "team_id, timestamp"),
                ("ix_usage_org_ts", "org_id, timestamp"),
                ("ix_usage_logs_event_id", "event_id"),
            ):
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON usage_logs ({cols})"))


def init_db(attempts: int = 15, delay_s: float = 2.0) -> None:
    """Create tables for any model registered on Base, then patch new columns.

    Retried because in a cluster the database may not be accepting connections
    yet when a pod starts, and several replicas starting together can race on
    CREATE TABLE -- the loser simply retries and finds the tables present.
    """
    import logging
    import time

    from app import models  # noqa: F401  (registers all mappers)

    for attempt in range(1, attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            _add_missing_columns()
            return
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts:
                raise
            logging.getLogger(__name__).warning(
                "database not ready (attempt %d/%d): %s", attempt, attempts, exc
            )
            time.sleep(delay_s)
