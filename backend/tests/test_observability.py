"""오류 수집이 **무엇을 안 보내는지**. 규약은 07-web-deployment.md §9.1.

비밀값과 회원의 글이 외부로 나가는 경로다. 주의력에 맡기지 않는다 —
`before_send` 가 무엇을 지우는지 직접 보고, 지우지 않으면 실패한다.
"""

import json
import secrets

import pytest

from app.config import get_settings
from app.observability import REDACTED, init_sentry, scrub


def event_with(**request) -> dict:
    """Sentry 가 FastAPI 요청에서 만들어 보내는 모양을 흉내 낸다."""
    return {
        "exception": {"values": [{"type": "KeyError", "value": "'example_ko'"}]},
        "request": {
            "url": "https://example.com/api/analyze",
            "method": "POST",
            **request,
        },
    }


def test_the_request_body_never_leaves():
    """분석 요청 본문에는 회원이 넣은 글 전체가, 키 등록 요청에는 평문 키가 있다."""
    event = scrub(event_with(data={"text": "회원이 분석한 사적인 글", "api_key": "AIzaSyREAL"}))

    assert "data" not in event["request"]
    assert "AIzaSyREAL" not in repr(event)
    assert "사적인 글" not in repr(event)


def test_cookies_never_leave():
    """세션 쿠키 하나로 그 회원을 가장할 수 있다."""
    event = scrub(event_with(cookies={"es_session": "eyJhbGciOi..."}))

    assert "cookies" not in event["request"]
    assert "eyJhbGciOi" not in repr(event)


def test_the_process_environment_never_leaves():
    """환경변수에는 ENCRYPTION_KEY 와 SESSION_SECRET 이 있다."""
    event = scrub(event_with(env={"ENCRYPTION_KEY": "정말비밀"}))

    assert "env" not in event["request"]
    assert "정말비밀" not in repr(event)


def test_headers_are_an_allow_list_not_a_deny_list():
    """금지 목록으로 두면 새 헤더가 생길 때마다 조용히 새어 나간다."""
    event = scrub(
        event_with(
            headers={
                "Content-Type": "application/json",
                "Cookie": "es_session=abc",
                "Authorization": "Bearer secret",
                "X-Future-Header": "아직 없는 헤더",
            }
        )
    )

    assert event["request"]["headers"] == {"Content-Type": "application/json"}


def test_anything_named_like_a_secret_is_wiped_even_when_nested():
    event = scrub(
        {
            "extra": {
                "harmless": "남는다",
                "api_key": "AIzaSyREAL",
                "inner": {"session_token": "tok", "level": "intermediate"},
            }
        }
    )

    assert event["extra"]["harmless"] == "남는다"
    assert event["extra"]["api_key"] == REDACTED
    assert event["extra"]["inner"]["session_token"] == REDACTED
    # 비밀값이 아닌 것은 그대로 둔다. 전부 지우면 보낼 이유가 없어진다.
    assert event["extra"]["inner"]["level"] == "intermediate"


def test_only_the_member_id_survives():
    """id 는 남긴다 — 한 명의 문제와 전원의 문제를 구별해야 한다.

    이메일과 IP 는 그 구별에 필요하지 않다.
    """
    event = scrub({"user": {"id": 7, "email": "a@b.com", "ip_address": "1.2.3.4"}})

    assert event["user"] == {"id": 7}


def test_what_is_worth_sending_survives():
    """다 지우면 보낼 이유가 없다. 스택과 경로는 남아야 한다."""
    event = scrub(event_with(headers={"Content-Type": "application/json"}, data={"text": "x"}))

    assert event["exception"]["values"][0]["type"] == "KeyError"
    assert event["request"]["url"].endswith("/api/analyze")
    assert event["request"]["method"] == "POST"


# ------------------------------------------------------------ 언제 켜지나


def _settings(monkeypatch, **env):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    return get_settings()


def test_it_stays_off_without_a_dsn(monkeypatch):
    """DSN 이 비면 아무것도 안 한다. 로컬 개발에서 켜질 일이 없어야 한다."""
    assert init_sentry(_settings(monkeypatch, APP_MODE="cloud", SENTRY_DSN="")) is False


def test_it_stays_off_in_local_even_with_a_dsn(monkeypatch):
    """두 겹으로 막는다 — `.env` 에 DSN 이 섞여 들어온 날을 위해서다 (09 §3.7)."""
    settings = _settings(monkeypatch, APP_MODE="local", SENTRY_DSN="https://x@y/1")

    assert init_sentry(settings) is False


def test_it_does_not_send_personal_data_by_default(monkeypatch):
    """`send_default_pii` 를 명시한다. 기본값에 기대면 SDK 가 바꿀 때 조용히 새어 나간다."""
    import sentry_sdk

    captured = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
    settings = _settings(monkeypatch, APP_MODE="cloud", SENTRY_DSN="https://x@y/1")

    assert init_sentry(settings) is True
    assert captured["send_default_pii"] is False
    assert captured["before_send"] is scrub
    # 성능 표본은 보내지 않는다. 알고 싶은 것은 "터졌는지" 하나다.
    assert captured["traces_sample_rate"] == 0.0


def test_the_release_is_the_deployed_commit(monkeypatch):
    """어느 커밋에서 났는지 모르면 고칠 데를 못 찾는다."""
    import sentry_sdk

    captured = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
    init_sentry(
        _settings(
            monkeypatch,
            APP_MODE="cloud",
            SENTRY_DSN="https://x@y/1",
            RENDER_GIT_COMMIT="abc1234",
        )
    )

    assert captured["release"] == "abc1234"


# ------------------------------------- 실제 예외를 흘려 본다 (07 §9.1.1)
#
# 위 검사들은 Sentry 가 보낼 이벤트 모양을 **손으로 흉내 낸** 것이다. 그것만 보면
# 통과하면서 틀린다 — 실제로 그랬다. 비밀값은 요청 칸이 아니라 **스택 프레임의
# 지역 변수**에 있었고, 거기는 들여다보지 않고 있었다.


@pytest.fixture
def captured(monkeypatch, tmp_path):
    """켜진 Sentry 가 실제로 내보내는 봉투를 가로챈다. 네트워크는 안 탄다."""
    import sentry_sdk

    from tests.modes import setup_env

    setup_env(monkeypatch, tmp_path, "cloud")
    monkeypatch.setenv("SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    get_settings.cache_clear()

    assert init_sentry(get_settings()) is True
    sent: list = []
    sentry_sdk.get_client().transport.capture_envelope = sent.append
    yield sent

    # 전역 클라이언트가 다음 테스트로 새지 않게 비운다.
    sentry_sdk.get_client().close()
    sentry_sdk.init(dsn=None)


def _sent_text(envelopes) -> str:
    return "".join(
        json.dumps(item.payload.json or {}, ensure_ascii=False)
        for envelope in envelopes
        for item in envelope.items
    )


def test_a_real_exception_carries_nothing_secret(captured):
    """**이 검사가 누출을 찾았다.**

    값을 소스에 박지 않고 실행 중에 만든다 — 박아 두면 Sentry 가 담는 코드 문맥
    (`post_context`)에 그대로 나타나 누출로 오인된다.
    """
    import sentry_sdk
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    marks = {name: secrets.token_hex(8).upper() for name in ("body", "key", "cookie", "header")}

    app = FastAPI()

    @app.post("/boom")
    def boom(payload: dict):
        raise KeyError("example_ko")

    with TestClient(app, raise_server_exceptions=False) as client:
        client.cookies.set("es_session", marks["cookie"])
        client.post(
            "/boom",
            json={"text": marks["body"], "api_key": marks["key"]},
            headers={"Authorization": f"Bearer {marks['header']}", "X-Future": "FUTURE"},
        )
    sentry_sdk.flush()

    blob = _sent_text(captured)
    assert blob, "아무것도 보내지 않았다 — 검사가 통과만 하고 있다"
    leaked = sorted(name for name, mark in marks.items() if mark in blob)
    assert not leaked, f"새어 나갔다: {leaked}"


def test_a_real_exception_still_carries_what_is_worth_sending(captured):
    """다 지우면 보낼 이유가 없다. 예외 종류와 경로는 남아야 한다."""
    import sentry_sdk
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/boom")
    def boom():
        raise KeyError("example_ko")

    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/boom")
    sentry_sdk.flush()

    blob = _sent_text(captured)
    assert "KeyError" in blob
    assert "example_ko" in blob
    assert "/boom" in blob
