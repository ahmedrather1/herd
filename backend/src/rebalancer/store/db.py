"""Database engine, session, and custom types for the persistence layer (A-3, D49).

SQLite via SQLModel (D23/D34). Design points:

- **Decimal money as exact TEXT (D45).** SQLite has no decimal type and floats are
  forbidden, so ``DecimalString`` stores every ``Decimal`` as its string form and rebuilds
  a ``Decimal`` on read. Models expose ``Decimal``; the DB keeps exact strings.
- **Single file, auto-created on first run.** The default DB lives at
  ``backend/data/rebalancer.db`` and its directory is created on demand. An optional
  ``REBALANCER_DB_URL`` env var overrides the location (used by tests to point at a temp
  DB); ``make_engine(url=...)`` also takes an explicit URL.
- **No migration framework in v1 (D49).** Schema evolves by drop-and-recreate during dev
  (no precious data yet); Alembic is adopted deliberately later.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from sqlalchemy import String
from sqlalchemy.engine import Engine
from sqlalchemy.types import TypeDecorator
from sqlmodel import Session, SQLModel, create_engine

from ..config import BACKEND_ROOT

# Single documented location for the local datastore (A-3). Git-ignored.
DEFAULT_DB_PATH = BACKEND_ROOT / "data" / "rebalancer.db"
DB_URL_ENV = "REBALANCER_DB_URL"


class DecimalString(TypeDecorator):
    """Persist ``Decimal`` as exact TEXT (D45) — never float; SQLite has no decimal type."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: str | None, dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


def _default_url() -> str:
    """Resolve the default DB URL: env override, else the pinned file path (dir created)."""
    override = os.environ.get(DB_URL_ENV)
    if override:
        return override
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH}"


def make_engine(url: str | None = None) -> Engine:
    """Create a SQLite engine. ``url`` defaults to the env override or the pinned file.

    ``check_same_thread=False`` because FastAPI offloads sync DB work to a threadpool
    (D46); SQLModel/SQLAlchemy manages access safely per-Session.
    """
    return create_engine(url or _default_url(), connect_args={"check_same_thread": False})


def create_db_and_tables(engine: Engine) -> None:
    """Create all tables (idempotent). Importing ``models`` registers them on the metadata."""
    from . import models  # noqa: F401  (import side effect: registers tables)

    SQLModel.metadata.create_all(engine)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Process-wide engine, tables ensured. Called at app startup (auto-create, A-3)."""
    engine = make_engine()
    create_db_and_tables(engine)
    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Transactional session: commit on success, roll back on error, always close."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
