"""09-mode-matrix.md 를 **설명이 아니라 명세로** 만든다.

통합한 지 커밋 하나 만에 주석 세 곳이 문서와 어긋났다(H-011). 사람이 문서를
챙기는 방식은 이미 실패했으므로, 문서의 표를 여기에 리터럴로 옮겨 두고
코드가 그 값을 내는지 확인한다. 값을 바꾸면 이 테스트가 깨지고,
고치려면 문서를 보게 된다.

**여기를 고칠 때는 09-mode-matrix.md 도 같이 고친다.**

[문서] 09-mode-matrix.md §6.2
"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.schemas import ABSOLUTE_MAX_INPUT_CHARS
from tests.modes import build_app, setup_env

# --- 09-mode-matrix.md §3.1 · §3.3 의 값 ---------------------------------------
DEFAULTS = {
    "local_max_input_chars": 2000,
    "cloud_max_input_chars": 800,
    "daily_analysis_limit": 60,
    "daily_practice_limit": 200,
}

# --- 09-mode-matrix.md §2: 모드별로 켜지고 꺼지는 것 -------------------------
MATRIX = {
    "local": {
        "requires_login": False,
        "max_input_chars": DEFAULTS["local_max_input_chars"],
        "daily_analysis_limit": 0,  # 한도 없음을 0 으로 알린다
        "daily_practice_limit": 0,
        "has_api_key_issue_url": False,
        "has_auth_routes": False,
        "has_account_deletion": False,  # §3.6 지울 계정이 없다
        "shares_one_provider": True,  # 3.2 앱당 하나
    },
    "cloud": {
        "requires_login": True,
        "max_input_chars": DEFAULTS["cloud_max_input_chars"],
        "daily_analysis_limit": DEFAULTS["daily_analysis_limit"],
        "daily_practice_limit": DEFAULTS["daily_practice_limit"],
        "has_api_key_issue_url": True,
        "has_auth_routes": True,
        "has_account_deletion": True,  # §3.6
        "shares_one_provider": False,  # 3.2 요청당 하나. 공유하면 남의 키로 호출된다
    },
}


def test_documented_defaults_match_the_code():
    """문서에 적힌 숫자가 `Settings` 의 기본값과 같은가.

    개발자의 `.env` 와 무관하게 **코드 기본값**을 본다.
    """
    for name, documented in DEFAULTS.items():
        assert Settings.model_fields[name].default == documented, (
            f"{name} 이 문서(09-mode-matrix.md)와 다르다. 둘 다 고쳐라."
        )


def test_mode_limits_stay_under_the_absolute_ceiling():
    """모드별 상한은 스키마의 절대 천장을 넘을 수 없다 (3.1)."""
    assert DEFAULTS["cloud_max_input_chars"] <= ABSOLUTE_MAX_INPUT_CHARS
    assert DEFAULTS["local_max_input_chars"] <= ABSOLUTE_MAX_INPUT_CHARS


@pytest.fixture(params=["local", "cloud"])
def mode_app(request, monkeypatch, tmp_path):
    """문서가 규정한 기본값으로 못박고 띄운다. 개발용 `.env` 에 흔들리지 않게 한다."""
    setup_env(monkeypatch, tmp_path, request.param)
    monkeypatch.setenv("LOCAL_MAX_INPUT_CHARS", str(DEFAULTS["local_max_input_chars"]))
    monkeypatch.setenv("CLOUD_MAX_INPUT_CHARS", str(DEFAULTS["cloud_max_input_chars"]))
    monkeypatch.setenv("DAILY_ANALYSIS_LIMIT", str(DEFAULTS["daily_analysis_limit"]))
    monkeypatch.setenv("DAILY_PRACTICE_LIMIT", str(DEFAULTS["daily_practice_limit"]))
    get_settings.cache_clear()
    app = build_app()
    with TestClient(app) as client:
        yield request.param, app, client


def test_api_config_matches_the_matrix(mode_app):
    """프론트는 모드를 묻지 않고 이 값들만 본다. 표와 어긋나면 화면이 어긋난다."""
    mode, _app, client = mode_app
    want = MATRIX[mode]
    body = client.get("/api/config").json()

    assert body["mode"] == mode
    assert body["requires_login"] is want["requires_login"]
    assert body["max_input_chars"] == want["max_input_chars"]
    assert body["daily_analysis_limit"] == want["daily_analysis_limit"]
    assert body["daily_practice_limit"] == want["daily_practice_limit"]
    assert bool(body["api_key_issue_url"]) is want["has_api_key_issue_url"]


def test_auth_routes_exist_only_in_cloud(mode_app):
    """라우터는 지연 등록되므로 `app.routes` 가 아니라 **응답**으로 확인한다.

    local 은 404(없는 경로), cloud 는 401(있지만 로그인 전).
    """
    mode, _app, client = mode_app
    exists = client.get("/api/auth/me").status_code != 404
    assert exists is MATRIX[mode]["has_auth_routes"]


def test_leaving_exists_only_where_there_is_an_account_to_delete(mode_app):
    """탈퇴는 `auth` 라우터에 있으므로 local 에서는 **경로 자체가 없다** (§3.6).

    기록 삭제는 두 모드 공통이라 여기서 갈리지 않는다.
    """
    mode, _app, client = mode_app
    assert (client.delete("/api/auth/account").status_code != 404) is MATRIX[mode][
        "has_account_deletion"
    ]
    # 기록 삭제는 두 모드 모두 **경로가 있다.** cloud 는 로그인 전이라 401 이지 404 가 아니다.
    assert client.delete("/api/account/data").status_code != 404, "기록 삭제는 두 모드 공통이다"


def test_provider_lifetime_matches_the_matrix(mode_app):
    """cloud 에서 프로바이더를 공유하면 **다른 회원의 키로 호출된다** (3.2)."""
    mode, app, _client = mode_app
    shared = getattr(app.state, "provider", None) is not None
    assert shared is MATRIX[mode]["shares_one_provider"]


def test_cors_credentials_only_in_cloud(mode_app):
    """세션 쿠키를 주고받는 cloud 에서만 켠다."""
    mode, app, _client = mode_app
    allow = next(
        m.kwargs["allow_credentials"] for m in app.user_middleware if "allow_credentials" in m.kwargs
    )
    assert allow is (mode == "cloud")


def test_both_modes_store_records_in_a_database(mode_app):
    """통합 뒤 두 모드 모두 DB 를 쓴다. 'local 은 DB 가 없다' 는 설명은 옛말이다 (H-011)."""
    _mode, _app, client = mode_app
    assert client.get("/api/history").status_code in (200, 401)
