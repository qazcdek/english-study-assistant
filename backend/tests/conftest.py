from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

# 검사가 나가도 되는 호스트. 로컬 모델 서버뿐이다.
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", ""})

# **진짜로 선을 타는 전송.** `MockTransport`(응답을 꽂는 검사)와 `ASGITransport`
# (`TestClient`)는 네트워크를 타지 않으므로 막지 않는다 — 막으면 멀쩡한 검사가
# 전부 깨진다. 실제로 그렇게 짰다가 프로바이더 검사 수십 개가 깨졌다.
REAL_TRANSPORTS = (httpx.HTTPTransport, httpx.AsyncHTTPTransport)


class OutboundCallInTest(RuntimeError):
    """검사가 **외부로 HTTP 를 보냈다.**

    규약은 하나다 — **검사는 실제 LLM 을 부르지 않는다.** 운영자 키의 무료 등급을
    검사가 조용히 깎기 때문이다. `H-048` 에서 실제로 그런 일이 있었다: 검사 설정이
    개발 `.env` 의 가디언 키를 들고 있어서, 운영자 플래그가 켜진 검사가
    `/api/articles/current` 를 칠 때마다 뒤에서 **진짜로 가디언과 Gemini 를** 불렀다.
    뒤에서 돌고 실패해도 쿨다운 표에만 적히므로 **검사는 통과하고 한도만 깎였다**
    (검사 시간 45초 → 27초가 그 차이였다).

    그래서 주의력에 맡기지 않고 **여기서 막는다** (`11 §2` 원리 ③ — 선언이 아니라
    장치로). 실제 응답으로 확인해야 하는 일은 **운영자에게 요청한다.**

    LLM 을 타는 검사는 `tests/fake_provider.py` 를 쓴다. 출처 호출을 보는 검사는
    `httpx.MockTransport` 로 응답을 꽂는다 (`test_grouping.py` · `test_picker.py`).
    """


@pytest.fixture(autouse=True)
def no_outbound_http(monkeypatch):
    """검사 중 외부 호스트로 나가는 HTTP 를 거부한다 (H-049).

    `httpx` 의 **보내는 한 지점**을 막는다 — 프로바이더와 가디언이 둘 다 `httpx` 를
    쓰므로 출처가 늘어도 이 장치는 그대로다. 막는 것은 **실제 전송뿐**이다:
    `MockTransport` 로 꽂은 응답과 `TestClient` 의 ASGI 호출은 선을 타지 않는다.
    """
    for client in (httpx.Client, httpx.AsyncClient):
        original = client.send

        def guard(self, request, *args, _original=original, **kwargs):
            host = request.url.host
            transport = getattr(self, "_transport", None)
            if isinstance(transport, REAL_TRANSPORTS) and host not in ALLOWED_HOSTS:
                raise OutboundCallInTest(
                    f"검사가 {host} 로 HTTP 를 보냈다. 검사는 외부 API 를 부르지 않는다 — "
                    "가짜 프로바이더나 httpx.MockTransport 를 쓰고, 실물 확인은 "
                    "운영자에게 요청한다."
                )
            return _original(self, request, *args, **kwargs)

        monkeypatch.setattr(client, "send", guard)


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

    # **출처 키를 비운다** (H-048). 개발 `.env` 에 실제 가디언 키가 있어서, 운영자
    # 플래그가 켜진 검사가 `/api/articles/current` 를 치면 뒤에서 도는 고르기가
    # **진짜로 가디언과 Gemini 를 불렀다.** 검사가 돈을 쓰고, 응답에 실제 기사가
    # 섞여 들어와 단정이 깨졌다.
    #
    # 키가 비면 `daily.should_run()` 이 첫 관문에서 멈춘다 — 끄는 장치를 그대로
    # 쓰는 것이다. 고르기를 검사하는 쪽은 `settings_with_key()` 로 일부러 채운다.
    monkeypatch.setenv("GUARDIAN_API_KEY", "")
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
