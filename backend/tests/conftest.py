import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture(params=["local", "cloud"])
def both_modes(request, monkeypatch, tmp_path):
    """**두 모드에서 모두** 도는 픽스처. 공통 기능 테스트는 이걸 쓴다.

    한쪽 모드에서만 고쳐 다른 쪽이 조용히 어긋나는 것을, 주의력이 아니라
    테스트가 막는다. 모드 전용 동작은 여기 말고 전용 픽스처를 쓴다.
    """
    from tests.modes import Api, build_app, owner_of, setup_env

    mode = request.param
    setup_env(monkeypatch, tmp_path, mode)
    with TestClient(build_app()) as client:
        yield Api(client=client, mode=mode, user_id=owner_of(client, mode))
