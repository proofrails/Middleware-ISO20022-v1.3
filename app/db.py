from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def _db_url() -> str:
    # Prefer Postgres if provided, otherwise fall back to local SQLite for dev
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # Dev fallback (will be overridden by docker-compose)
    return "sqlite:///./dev.db"


DATABASE_URL = _db_url()
ECHO = os.getenv("SQL_ECHO", "0") in {"1", "true", "TRUE", "yes", "on"}

engine_kwargs = {"echo": ECHO, "future": True}

if DATABASE_URL.startswith("sqlite"):
    # Needed for SQLite in multithreaded FastAPI dev
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()
