"""웹 배포(cloud) 모드: 로그인 · 동의 · 회원 키 · 사용량 · 저장."""

import pytest
from fastapi.testclient import TestClient

from app.auth.crypto import KeyCipher
from app.auth.session import COOKIE_NAME, issue_token
from app.config import get_settings
from app.db import User, session_scope
from app.deps import get_provider
from app.main import create_app
from tests.fake_provider import FakeProvider

SESSION_SECRET = "x" * 40
ENCRYPTION_KEY = KeyCipher.generate_key()


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_MODE", "cloud")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setenv("ENCRYPTION_KEY", ENCRYPTION_KEY)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as client:
        yield client


def make_user(*, consented=True, with_key=True) -> int:
    with session_scope() as db:
        user = User(google_sub="sub-1", email="a@b.com", name="테스터")
        if consented:
            from app.db.models import utcnow

            user.consented_at = utcnow()
        if with_key:
            user.encrypted_api_key = KeyCipher(ENCRYPTION_KEY).encrypt("AIzaSyFAKEKEY0000")
            user.api_key_hint = "••••0000"
        db.add(user)
        db.flush()
        return user.id


def login(client: TestClient, user_id: int) -> None:
    client.cookies.set(COOKIE_NAME, issue_token(user_id, SESSION_SECRET, 30))


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


def test_analysis_is_saved_and_counted(cloud):
    user_id = make_user()
    login(cloud, user_id)

    assert cloud.post("/api/analyze", json={"text": "across the pond"}).status_code == 200

    usage = cloud.get("/api/usage").json()
    assert usage["analyses"] == 1

    history = cloud.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["source_text"] == "across the pond"

    detail = cloud.get(f"/api/history/{history[0]['id']}").json()
    assert detail["result"]["overview"]["domain"] == "경제·금융 시사 논평"


def test_daily_limit_blocks_further_analysis(cloud, monkeypatch):
    monkeypatch.setenv("DAILY_ANALYSIS_LIMIT", "1")
    get_settings.cache_clear()
    login(cloud, make_user())

    assert cloud.post("/api/analyze", json={"text": "first"}).status_code == 200
    resp = cloud.post("/api/analyze", json={"text": "second"})

    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "usage_limit"


def test_practice_is_saved(cloud):
    login(cloud, make_user())
    resp = cloud.post(
        "/api/practice",
        json={
            "expression": "across the pond",
            "meaning": "대서양을 건너",
            "prompt_ko": "그녀의 소설은 대서양을 건너갔다.",
            "model_answer": "Her novel made it across the pond.",
            "learner_answer": "Her novel went across the pond",
        },
    )
    assert resp.status_code == 200

    rows = cloud.get("/api/practice/history").json()
    assert len(rows) == 1
    assert rows[0]["expression"] == "across the pond"
    assert rows[0]["verdict"] == "통함"


# --------------------------------------------------------------------- 단어장


def test_vocabulary_add_list_delete(cloud):
    login(cloud, make_user())
    item = {"expression": "sum up", "type": "Phrasal Verb", "meaning": "요약하다"}

    created = cloud.post("/api/vocabulary", json=item).json()
    assert created["expression"] == "sum up"

    # 같은 표현을 다시 담으면 새로 쌓이지 않고 갱신된다.
    cloud.post("/api/vocabulary", json={**item, "meaning": "요약하다, 정리하다"})
    rows = cloud.get("/api/vocabulary").json()
    assert len(rows) == 1
    assert rows[0]["meaning"] == "요약하다, 정리하다"

    assert cloud.delete(f"/api/vocabulary/{rows[0]['id']}").status_code == 200
    assert cloud.get("/api/vocabulary").json() == []


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
    assert cloud.get(f"/api/history/{record_id}").status_code == 400


# --------------------------------------------------------------------- 로컬 모드


def test_local_mode_has_no_auth_routes(monkeypatch):
    monkeypatch.setenv("APP_MODE", "local")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as client:
        assert client.get("/api/auth/me").status_code == 404
        # 로그인 없이 바로 분석된다.
        assert client.post("/api/analyze", json={"text": "hello"}).status_code == 200
