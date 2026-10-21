"""DB 엔진과 세션. **두 모드 모두** 쓴다 — local 은 docker Postgres, cloud 는 Neon."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def normalize_url(database_url: str) -> str:
    """Render/Neon 이 주는 `postgres://` 를 SQLAlchemy 2.x 가 아는 형태로 바꾼다.

    엔진과 Alembic 이 **같은 변환**을 써야 한다. 한쪽만 고치면 마이그레이션이
    다른 DB 를 보게 된다.
    """
    for prefix in ("postgres://", "postgresql://"):
        if database_url.startswith(prefix):
            return database_url.replace(prefix, "postgresql+psycopg://", 1)
    return database_url


def init_engine(database_url: str, *, create_all: bool = False) -> Engine:
    """엔진을 만든다.

    `create_all` 은 **기본으로 꺼져 있다.** 스키마는 Alembic 이 만든다
    (`app/db/migrate.py`). 켜 두면 마이그레이션 없이도 테이블이 생겨
    **둘이 어긋난 것을 아무도 모르게 된다.**
    """
    global _engine, _SessionLocal

    database_url = normalize_url(database_url)

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
        raise RuntimeError("DB 가 초기화되지 않았습니다. init_engine() 이 먼저 불려야 합니다.")
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
