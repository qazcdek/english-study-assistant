import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    """테스트는 개발용 Postgres 를 건드리지 않는다.

    분석 기록을 DB 에 남기게 되면서 테스트가 실제 DB 에 행을 쌓았다.
    테스트마다 빈 SQLite 파일을 쓰게 해 서로 간섭하지 않도록 한다.
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
