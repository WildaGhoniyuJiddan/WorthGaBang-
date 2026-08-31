from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        # timeout: tunggu lock proses lain (pipeline PC & laptop jalan paralel);
        # WAL biar reader gak diblokir writer.
        return {"connect_args": {"check_same_thread": False, "timeout": 30},
                "pool_pre_ping": True}
    return {"pool_pre_ping": True}


settings = get_settings()
database_url = settings.database_url
# Use psycopg3 (already a dependency) instead of the default psycopg2 driver.
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
if database_url.startswith("sqlite:///./"):
    database_path = Path(__file__).resolve().parents[1] / database_url.removeprefix("sqlite:///./")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{database_path.as_posix()}"

engine = create_engine(database_url, future=True, **_engine_kwargs(database_url))

from sqlalchemy import event


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _record):
    if database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
