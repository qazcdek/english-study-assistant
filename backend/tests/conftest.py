from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def db_url(tmp_path) -> Iterator[str]:
    """이 테스트가 쓸 **빈 DB 하나.** 기본 SQLite, `TEST_DATABASE_URL` 이 있으면 Postgres.

    **주소를 정하는 곳이 하나여야 한다.** 전에는 네 군데가 각자
    `sqlite+pysqlite:///{tmp_path}/…` 를 적고 있었다 — 한 곳만 Postgres 로 돌려도
    나머지 셋은 SQLite 에 남아서, 운영 엔진을 본다고 믿는 상태가 된다 (H-032).

    무엇을 고르고 왜 스키마로 가두는지는 `tests/dbs.py`.
    """
    from tests import dbs

    with dbs.empty_database(tmp_path) as url:
        yield url


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, db_url):
    """테스트마다 설정 캐시를 비우고, 개발용 DB 를 건드리지 않게 가둔다.

    두 모드 모두 분석 기록을 DB 에 남기므로 테스트도 DB 를 쓴다.
    테스트마다 빈 DB 를 주어 서로 간섭하지 않도록 한다.
    cloud 테스트는 이 위에서 APP_MODE 등을 다시 덮어쓴다.
    """
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(params=["local", "cloud"])
def both_modes(request, monkeypatch):
    """**두 모드에서 모두** 도는 픽스처. 공통 기능 테스트는 이걸 쓴다.

    한쪽 모드에서만 고쳐 다른 쪽이 조용히 어긋나는 것을, 주의력이 아니라
    테스트가 막는다. 모드 전용 동작은 여기 말고 전용 픽스처를 쓴다.
    """
    from tests.modes import Api, build_app, owner_of, setup_env

    mode = request.param
    setup_env(monkeypatch, mode)
    with TestClient(build_app()) as client:
        yield Api(client=client, mode=mode, user_id=owner_of(client, mode))


@pytest.fixture
def cloud(monkeypatch):
    """cloud **전용** 픽스처. 두 모드 공통 기능은 `both_modes` 로 간다.

    `test_cloud.py` 안에만 있던 것을 올렸다. 회원 데이터 격리 검사도 회원이 둘인
    상황을 세워야 하고, 같은 픽스처를 두 파일이 각자 들면 갈라진다.
    """
    from tests.modes import build_app, setup_env

    setup_env(monkeypatch, "cloud")
    with TestClient(build_app()) as client:
        yield client
