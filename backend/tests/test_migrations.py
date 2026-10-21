"""마이그레이션이 모델과 어긋나지 않는지 본다.

`create_all` 을 쓰던 동안에는 **모델을 고치면 테이블이 자동으로 따라왔다.** Alembic 으로
옮기면 그 자동이 사라진다 — 모델만 고치고 리비전을 안 만들면 배포본 스키마가 뒤처지는데,
테스트는 전부 통과한다. 그 구멍을 여기서 막는다.
"""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.db.migrate import upgrade_to_head
from app.db.models import Base

TABLES = {table.name for table in Base.metadata.sorted_tables}


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path}/m.db"
    monkeypatch.setenv("APP_MODE", "local")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()


def test_upgrade_creates_every_table(fresh_db):
    upgrade_to_head()
    engine = create_engine(fresh_db)
    try:
        assert TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_the_migration_matches_the_models(fresh_db):
    """리비전을 올린 DB 와 모델 사이에 차이가 없어야 한다.

    모델을 고치고 리비전을 안 만들면 여기서 **그 차이가 그대로 찍혀** 실패한다.
    고치는 법: `alembic revision --autogenerate -m "무엇을 바꿨는지"`.
    """
    upgrade_to_head()
    engine = create_engine(fresh_db)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()

    assert not diff, f"모델과 마이그레이션이 어긋났다. 리비전을 만들어라:\n{diff}"


def test_an_old_create_all_database_is_stamped_instead_of_upgraded(fresh_db):
    """`create_all` 로 이미 만들어진 DB 에 `upgrade` 를 걸면 '이미 있는 테이블' 로 깨진다.

    그 DB 는 첫 리비전을 찍고 넘어가야 한다 (`app/db/migrate.py`).
    """
    engine = create_engine(fresh_db)
    Base.metadata.create_all(engine)
    assert "alembic_version" not in set(inspect(engine).get_table_names())
    engine.dispose()

    upgrade_to_head()  # 깨지지 않아야 한다

    engine = create_engine(fresh_db)
    try:
        assert "alembic_version" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_the_image_carries_what_the_migration_runner_needs():
    """`alembic.ini` 와 `migrations/` 가 이미지에 없으면 **배포본이 부팅하다 죽는다.**

    처음 넣을 때 실제로 빠뜨렸다. Dockerfile 은 `backend/app` 만 복사하고 있었다.
    """
    from app.db.migrate import ALEMBIC_INI

    dockerfile = (ALEMBIC_INI.parents[1] / "Dockerfile").read_text(encoding="utf-8")
    for needed in ("backend/alembic.ini", "backend/migrations"):
        assert f"COPY {needed}" in dockerfile, f"Dockerfile 이 {needed} 를 복사하지 않는다"
