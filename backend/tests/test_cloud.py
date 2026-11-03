"""웹 배포(cloud) 모드: 로그인 · 동의 · 회원 키 · 사용량 · 저장."""

from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.auth.session import COOKIE_NAME
from app.config import Settings, get_settings
from app.db import User, session_scope
from app.providers import registry
from app.providers.base import CompletionResult
from tests.modes import SESSION_SECRET, build_app, login
from tests.modes import make_cloud_user as make_user

__all__ = ["SESSION_SECRET"]


# --------------------------------------------------------------------- 인증 문턱


def test_analyze_requires_login(cloud):
    resp = cloud.post("/api/analyze", json={"text": "hello"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth_required"


def test_analyze_requires_consent(cloud):
    login(cloud, make_user(consented=False))
    resp = cloud.post("/api/analyze", json={"text": "hello"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "consent_required"


def test_analyze_requires_api_key(cloud):
    """동의만 하고 키를 안 넣으면 분석할 수 없다. 호출은 회원 키로 이뤄지기 때문이다."""
    login(cloud, make_user(with_key=False))
    resp = cloud.post("/api/analyze", json={"text": "hello"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "api_key_required"


def test_me_reports_account_state(cloud):
    login(cloud, make_user())
    body = cloud.get("/api/auth/me").json()
    assert body["email"] == "a@b.com"
    assert body["has_consented"] is True
    assert body["has_api_key"] is True
    assert body["api_key_hint"] == "••••0000"


def test_api_key_is_never_returned(cloud):
    login(cloud, make_user())
    assert "AIzaSy" not in cloud.get("/api/auth/me").text


# --------------------------------------------------------------------- 사용량


def test_daily_limit_blocks_further_analysis(cloud, monkeypatch):
    monkeypatch.setenv("DAILY_ANALYSIS_LIMIT", "1")
    get_settings.cache_clear()
    login(cloud, make_user())

    assert cloud.post("/api/analyze", json={"text": "first"}).status_code == 200
    resp = cloud.post("/api/analyze", json={"text": "second"})

    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "usage_limit"


# --------------------------------------------------------------------- 남의 기록


def test_user_cannot_read_another_users_record(cloud):
    owner = make_user()
    login(cloud, owner)
    cloud.post("/api/analyze", json={"text": "mine"})
    record_id = cloud.get("/api/history").json()[0]["id"]

    with session_scope() as db:
        other = User(google_sub="sub-2", email="c@d.com")
        db.add(other)
        db.flush()
        other_id = other.id

    login(cloud, other_id)
    # 없는 기록과 같은 답이다. 다르게 답하면 id 로 존재를 알아낼 수 있다 (03 · 14 §3.1).
    assert cloud.get(f"/api/history/{record_id}").status_code == 404


# --------------------------------------------------------------------- 로컬 모드


def test_local_mode_has_no_auth_routes(monkeypatch):
    monkeypatch.setenv("APP_MODE", "local")
    get_settings.cache_clear()
    with TestClient(build_app()) as client:
        assert client.get("/api/auth/me").status_code == 404
        # 로그인 없이 바로 분석된다.
        assert client.post("/api/analyze", json={"text": "hello"}).status_code == 200


def test_spa_fallback_does_not_swallow_api_404(monkeypatch, tmp_path):
    """빌드된 프론트를 같은 오리진에서 서빙할 때, /api 미매칭은 HTML 이 아니라 404 여야 한다."""
    import app.main as main_module

    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>spa</html>")

    monkeypatch.setattr(main_module, "_static_dir", lambda: static)
    monkeypatch.setenv("APP_MODE", "local")
    get_settings.cache_clear()

    with TestClient(main_module.create_app()) as client:
        assert client.get("/api/nope").status_code == 404
        assert client.get("/some/route").text == "<html>spa</html>"


def test_cloud_input_limit_is_narrower(cloud):
    """회원 각자의 Gemini 한도를 소모하므로 local(2000자)보다 좁다 (09-mode-matrix.md §3.1)."""
    from app.config import get_settings

    login(cloud, make_user())
    limit = get_settings().max_input_chars

    assert limit == 1200
    assert cloud.post("/api/analyze", json={"text": "a" * limit}).status_code == 200
    assert cloud.post("/api/analyze", json={"text": "a" * (limit + 1)}).status_code == 422
    assert cloud.get("/api/config").json()["max_input_chars"] == limit


def test_reading_records_does_not_require_consent_or_key(cloud):
    """동의와 API 키는 LLM 을 부를 때 필요한 것이지, 저장된 기록을 읽는 데 필요한 것이 아니다."""
    login(cloud, make_user(consented=False, with_key=False))

    assert cloud.get("/api/history").status_code == 200
    assert cloud.get("/api/vocabulary").status_code == 200
    # 분석은 여전히 막힌다
    assert cloud.post("/api/analyze", json={"text": "a" * 30}).status_code == 403


# ------------------------------------------------------------------------ 탈퇴


def test_leaving_removes_the_account_and_its_data(cloud):
    user_id = make_user()
    login(cloud, user_id)
    cloud.post("/api/analyze", json={"text": "across the pond"})

    deleted = cloud.delete("/api/auth/account")
    assert deleted.status_code == 200
    assert deleted.json()["analyses"] == 1

    with session_scope() as db:
        assert db.get(User, user_id) is None

    # 쿠키까지 지워지므로 같은 클라이언트로 더 못 들어간다.
    assert cloud.get("/api/auth/me").status_code == 401


def test_leaving_takes_the_encrypted_keys_with_it(cloud):
    """키는 이제 **따로 있는 표**에 있다. 탈퇴가 그것까지 지워야 한다 (M12-T2).

    전에는 계정 행에 있어서 계정을 지우면 함께 사라졌다. 표가 갈리면서 그 보장이
    사라졌다 — `OWNED` 에 넣지 않으면 **탈퇴한 회원의 암호화된 키가 남는다.**
    """
    from app.db import ProviderKey

    user_id = make_user()
    login(cloud, user_id)

    with session_scope() as db:
        assert db.query(ProviderKey).filter(ProviderKey.user_id == user_id).count() == 1

    cloud.delete("/api/auth/account")

    with session_scope() as db:
        assert db.query(User).filter(User.id == user_id).count() == 0
        assert db.query(ProviderKey).filter(ProviderKey.user_id == user_id).count() == 0


def test_clearing_records_keeps_the_key(cloud):
    """**기록 삭제는 키를 건드리지 않는다.**

    `OWNED` 한 상수로 두 범위를 겸하다가 실제로 틀렸다 — 기록을 비우니 키까지
    사라져 그다음 분석이 403 이 났다 (M12-T2).
    """
    from app.db import ProviderKey

    user_id = make_user()
    login(cloud, user_id)
    cloud.post("/api/analyze", json={"text": "across the pond"})

    cloud.delete("/api/account/data")

    with session_scope() as db:
        assert db.query(ProviderKey).filter(ProviderKey.user_id == user_id).count() == 1
    assert cloud.post("/api/analyze", json={"text": "across the pond"}).status_code == 200


def test_leaving_requires_login(cloud):
    assert cloud.delete("/api/auth/account").status_code == 401


# ------------------------------------------- 키 등록은 **고른 제공자**를 따른다 (H-037)
#
# 확인 분기가 `if provider_id == GEMINI` 하나였다. OpenAI·Anthropic 은 **무검증으로**
# 저장됐고, 화면까지 제공자와 무관하게 Gemini 키를 요구했으므로 **Gemini 키가 OpenAI
# 키 자리에** 들어갔다. 분석을 눌러야 그걸 알 수 있었다.


class _Probe:
    """키 확인이 **실제로 제공자를 불렀나.** 네트워크로 나가지 않는다."""

    def __init__(self, *, ok: bool) -> None:
        self.ok = ok
        self.called = False

    async def complete(self, messages, **kwargs) -> CompletionResult:
        self.called = True
        if not self.ok:
            raise RuntimeError("401 Unauthorized")
        return CompletionResult(text="ok", model="probe")

    async def aclose(self) -> None:
        pass


# **목록에서 끌어온다.** 여기에 셋을 적으면 네 번째 제공자가 들어올 때
# 조용히 빠진다 — 그게 이 결함이 생긴 방식이다.
NEEDS_KEY = [p.id for p in registry.PROVIDERS if p.needs_key and p.implemented]


@pytest.mark.parametrize("provider_id", NEEDS_KEY)
def test_a_key_is_verified_for_every_provider_that_needs_one(cloud, monkeypatch, provider_id):
    """하나만 확인하면 **나머지는 무검증 저장**이다."""
    login(cloud, make_user(with_key=False))
    assert cloud.put("/api/account/settings", json={"provider": provider_id}).status_code == 200

    probe = _Probe(ok=False)
    monkeypatch.setattr(registry, "build", lambda *a, **k: probe)

    resp = cloud.put("/api/account/api-key", json={"api_key": "bogus-key-0000"})

    assert probe.called, f"{provider_id}: 키를 확인도 하지 않고 받았다"
    assert resp.status_code == 400
    assert cloud.get("/api/account/settings").json()["keys"] == {}


@pytest.mark.parametrize("provider_id", NEEDS_KEY)
def test_a_key_is_stored_under_the_chosen_provider(cloud, monkeypatch, provider_id):
    """제공자를 안 주면 **지금 고른 것**으로 간다. 화면이 그 사실을 보여줘야 한다."""
    login(cloud, make_user(with_key=False))
    cloud.put("/api/account/settings", json={"provider": provider_id})
    monkeypatch.setattr(registry, "build", lambda *a, **k: _Probe(ok=True))

    body = cloud.put("/api/account/api-key", json={"api_key": "some-key-1234"}).json()

    assert body["keys"] == {provider_id: "••••1234"}
    assert body["ready"] is True


# --------------------------------- 로그인 쿠키가 실리는 호스트 (H-044)
#
# 콜백이 세션 쿠키를 `PUBLIC_BASE_URL` 의 호스트에 심고 `FRONTEND_BASE_URL` 로
# 보낸다. 쿠키는 **포트는 무시하지만 호스트 이름은 구분한다** — 둘이 갈리면
# 로그인이 **오류 없이** 안 된다. 콜백은 303 으로 잘 돌아오고 화면만 다시
# 로그인 화면이다. 그래서 선언이 아니라 **검사로** 건다 (11 §2 원리 ③).


def _origin(url: str) -> tuple[str, str]:
    """스킴과 호스트만. **포트는 뺀다** — 쿠키가 포트를 구분하지 않는다."""
    parsed = urlparse(url)
    return parsed.scheme, (parsed.hostname or "")


def test_the_two_base_urls_share_a_scheme_and_host_by_default():
    """코드 기본값만으로 cloud 를 띄워도 로그인이 되어야 한다."""
    assert _origin(Settings.model_fields["public_base_url"].default) == _origin(
        Settings.model_fields["frontend_base_url"].default
    )


def test_the_env_example_does_not_hand_out_a_broken_pair():
    """**사람들이 복사하는 파일이 이쪽이다.** 기본값만 고치면 예제가 남는다."""
    example = Path(__file__).resolve().parent.parent / ".env.example"
    values = {}
    for line in example.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(("PUBLIC_BASE_URL=", "FRONTEND_BASE_URL=")):
            key, value = line.split("=", 1)
            values[key] = value

    assert set(values) == {"PUBLIC_BASE_URL", "FRONTEND_BASE_URL"}, values
    assert _origin(values["PUBLIC_BASE_URL"]) == _origin(values["FRONTEND_BASE_URL"]), (
        f"호스트가 갈리면 로그인이 조용히 안 된다: {values}"
    )


def test_the_session_cookie_is_not_secure_over_plain_http(cloud):
    """`secure` 는 `PUBLIC_BASE_URL` 에서 끌어온다 — http 개발에서 켜지면 안 실린다."""
    login(cloud, make_user())
    jar = cloud.cookies.jar
    cookie = next(c for c in jar if c.name == COOKIE_NAME)

    assert cookie.secure is False
