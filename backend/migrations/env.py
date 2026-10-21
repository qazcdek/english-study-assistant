"""Alembic 실행 환경.

**URL 을 `alembic.ini` 에 적지 않는다.** 앱 설정(`APP_MODE` 와 `DATABASE_URL`)에서
읽어 `normalize_url` 로 같은 변환을 거친다. 엔진과 다른 길로 가면 마이그레이션이
엉뚱한 DB 를 고친다.
"""

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db.models import Base
from app.db.session import normalize_url

target_metadata = Base.metadata


def _url() -> str:
    return normalize_url(get_settings().database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite 는 ALTER 가 제한적이라 테이블을 다시 만들어야 한다.
            render_as_batch=url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
