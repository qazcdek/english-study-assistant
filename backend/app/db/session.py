"""DB 엔진과 세션. cloud 모드에서만 초기화된다."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(database_url: str, *, create_all: bool = True) -> Engine:
    global _engine, _SessionLocal

    # Render/Neon 이 주는 postgres:// 를 SQLAlchemy 2.x 가 아는 형태로 바꾼다.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    kwargs: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

    _engine = create_engine(database_url, **kwargs)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    if create_all:
        Base.metadata.create_all(_engine)
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI 의존성."""
    if _SessionLocal is None:
        raise RuntimeError("DB 가 초기화되지 않았습니다 (APP_MODE=cloud 인지 확인하세요).")
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    if _SessionLocal is None:
        raise RuntimeError("DB 가 초기화되지 않았습니다.")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
