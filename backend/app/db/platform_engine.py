from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.metadata_db import is_sqlite_metadata_url


def _sqlite_connect_args(database_url: str) -> dict:
    if not is_sqlite_metadata_url(database_url):
        return {}
    return {"check_same_thread": False}


def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA journal_mode=DELETE")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


@lru_cache(maxsize=4)
def get_platform_engine(database_url: str) -> Engine:
    url = (database_url or "").strip()
    engine = create_engine(
        url,
        pool_pre_ping=not is_sqlite_metadata_url(url),
        future=True,
        connect_args=_sqlite_connect_args(url),
    )
    if is_sqlite_metadata_url(url):

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection, connection_record) -> None:  # noqa: ARG001
            _configure_sqlite_connection(dbapi_connection, connection_record)

    return engine


def get_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_platform_engine(database_url), expire_on_commit=False)
