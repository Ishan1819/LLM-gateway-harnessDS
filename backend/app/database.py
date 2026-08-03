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


def init_db() -> None:
    """Create tables for any model registered on Base, then patch new columns."""
    from app import models  # noqa: F401  (registers all mappers)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
