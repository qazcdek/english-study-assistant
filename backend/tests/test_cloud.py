"""웹 배포(cloud) 모드: 로그인 · 동의 · 회원 키 · 사용량 · 저장."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import User, session_scope
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

    assert limit == 800
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
