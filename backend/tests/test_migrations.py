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


# ------------------------------------- 옮겨도 복호화되나 (M12-T2)
#
# 이 리비전의 위험은 **구조가 아니라 데이터**다. autogenerate 는 열을 만들고 지우기만
# 하고 값을 옮기지 않는다 — 그대로 돌리면 모든 회원의 키가 사라지고, `ENCRYPTION_KEY`
# 는 교체할 수 없으므로 복구할 길도 없다. 그래서 **진짜 Fernet 토막**으로 왕복한다.

LEGACY_REVISION = "c80f88bac834"
PLAINTEXT = "AIzaSyREAL-KEY-THAT-MUST-SURVIVE-0000"


def _at_legacy_revision(url: str):
    """옛 스키마(제공자 하나였던 시절)까지만 올린 DB."""
    from alembic import command

    from app.db.migrate import _config

    command.upgrade(_config(), LEGACY_REVISION)
    return create_engine(url)


def _seed_legacy_member(engine, encrypted: str, hint: str) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (google_sub, email, name, picture, encrypted_api_key,"
                " api_key_hint, created_at, last_login_at)"
                " VALUES ('sub-legacy', 'a@b.com', '', '', :enc, :hint,"
                " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"enc": encrypted, "hint": hint},
        )


def test_an_existing_key_still_decrypts_after_the_move(fresh_db):
    """**옮겨도 복호화되는지**를 실제 토막으로 확인한다.

    글자가 같은지만 보면 모자라다 — 옮기는 과정에서 인코딩이나 열 종류가 바뀌어도
    문자열 비교는 통과할 수 있다. 실제로 **풀리는지**를 본다.

    (길이를 좁히는 사고는 `test_the_migration_matches_the_models` 가 먼저 잡는다.
    재 보니 SQLite 는 길이를 무시하고 Postgres 는 거부하므로, **짧은 열은 테스트를
    통과하고 배포 때 마이그레이션이 죽는다.**)
    """
    from alembic import command
    from sqlalchemy import text

    from app.auth.crypto import KeyCipher
    from app.db.migrate import _config

    key = KeyCipher.generate_key()
    cipher = KeyCipher(key)
    encrypted = cipher.encrypt(PLAINTEXT)

    engine = _at_legacy_revision(fresh_db)
    _seed_legacy_member(engine, encrypted, "••••0000")

    command.upgrade(_config(), "head")

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT provider, encrypted, hint FROM provider_keys")
        ).all()

    assert len(rows) == 1, "키가 옮겨지지 않았다"
    provider, moved, hint = rows[0]
    assert provider == "gemini", "제공자가 하나였던 시절의 키는 전부 Gemini 것이다"
    assert hint == "••••0000"
    # **여기가 핵심이다.** 글자가 같은지가 아니라 실제로 풀리는지를 본다.
    assert cipher.decrypt(moved) == PLAINTEXT


def test_a_member_without_a_key_gets_no_row(fresh_db):
    """빈 행을 만들면 "키가 있다" 로 보이고, 분석이 키 없이 시작된다."""
    from alembic import command
    from sqlalchemy import text

    from app.db.migrate import _config

    engine = _at_legacy_revision(fresh_db)
    _seed_legacy_member(engine, "", "")

    command.upgrade(_config(), "head")

    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM provider_keys")).scalar()

    assert count == 0


def test_rolling_back_puts_the_key_back(fresh_db):
    """**구조만 되돌리면 키가 사라진다.** 배포를 물려야 하는 날 발견하면 늦다."""
    from alembic import command
    from sqlalchemy import text

    from app.auth.crypto import KeyCipher
    from app.db.migrate import _config

    cipher = KeyCipher(KeyCipher.generate_key())
    encrypted = cipher.encrypt(PLAINTEXT)

    engine = _at_legacy_revision(fresh_db)
    _seed_legacy_member(engine, encrypted, "••••0000")
    command.upgrade(_config(), "head")

    command.downgrade(_config(), LEGACY_REVISION)

    with engine.connect() as conn:
        back = conn.execute(text("SELECT encrypted_api_key FROM users")).scalar()

    assert cipher.decrypt(back) == PLAINTEXT
