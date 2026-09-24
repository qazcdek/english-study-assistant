import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    """테스트마다 설정 캐시를 비우고, 개발용 Postgres 를 건드리지 않게 가둔다.

    두 모드 모두 분석 기록을 DB 에 남기므로 테스트도 DB 를 쓴다.
    테스트마다 빈 SQLite 파일을 주어 서로 간섭하지 않도록 한다.
    cloud 테스트는 이 위에서 APP_MODE 등을 다시 덮어쓴다.
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
