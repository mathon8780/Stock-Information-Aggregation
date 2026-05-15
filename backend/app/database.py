from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _connect_args() -> dict[str, object]:
    if settings.database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


if settings.database_url.startswith("sqlite:///"):
    db_path = Path(settings.database_url.replace("sqlite:///", "", 1))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, connect_args=_connect_args(), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from app.models import entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _upgrade_existing_schema()


def _upgrade_existing_schema() -> None:
    inspector = inspect(engine)
    if "news" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("news")}
    columns = {
        "original_title": "VARCHAR(240)",
        "simplification_status": "VARCHAR(16) NOT NULL DEFAULT 'pending'",
        "simplified_at": "TIMESTAMPTZ",
        "llm_provider": "VARCHAR(64)",
        "llm_model": "VARCHAR(128)",
        "prompt_name": "VARCHAR(64)",
        "error_message": "TEXT",
    }
    with engine.begin() as connection:
        for name, ddl_type in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE news ADD COLUMN {name} {ddl_type}"))
        connection.execute(text("UPDATE news SET original_title = substr(title, 1, 240) WHERE original_title IS NULL OR original_title = ''"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
