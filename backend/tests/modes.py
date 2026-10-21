"""두 모드를 똑같이 띄우기 위한 공용 장치.

로컬과 웹을 한 코드베이스로 합친 뒤에도 **테스트는 한쪽에서만 돌고 있었다.**
80개 중 64개가 기본값(local)으로만 돌아서, 두 모드 공통 기능을 local 에서
깨뜨려도 잡히지 않았다 (09-mode-matrix.md 6.1).

그래서 공통 기능 테스트는 `both_modes` 픽스처로 **두 모드에서 모두** 돈다.
모드 전용 동작만 전용 픽스처(`test_cloud.py` 의 `cloud`)를 쓴다.
"""

from typing import Literal, NamedTuple

from fastapi.testclient import TestClient

from app.auth.crypto import KeyCipher
from app.auth.session import COOKIE_NAME, issue_token
from app.config import get_settings
from app.db import User, session_scope
from app.deps import LOCAL_USER_ID, get_provider
from app.main import create_app
from tests.fake_provider import FakeProvider

Mode = Literal["local", "cloud"]

SESSION_SECRET = "x" * 40
ENCRYPTION_KEY = KeyCipher.generate_key()


class Api(NamedTuple):
    """어느 모드에서든 '요청의 주인으로 API 를 부를 수 있는 상태'."""

    client: TestClient
    mode: Mode
    user_id: int


def setup_env(monkeypatch, tmp_path, mode: Mode) -> None:
    """모드별 환경변수를 세운다.

    `APP_MODE` 를 **두 모드 모두 명시적으로** 설정한다. 생략하면 개발용 `.env` 의
    값을 읽어 테스트가 돌리는 모드와 달라질 수 있다.
    """
    monkeypatch.setenv("APP_MODE", mode)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/test.db")
    if mode == "cloud":
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("SESSION_SECRET", SESSION_SECRET)
        monkeypatch.setenv("ENCRYPTION_KEY", ENCRYPTION_KEY)
    get_settings.cache_clear()


def build_app(provider: FakeProvider | None = None):
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider or FakeProvider()
    return app


def make_cloud_user(*, consented: bool = True, with_key: bool = True) -> int:
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


def owner_of(client: TestClient, mode: Mode) -> int:
    """그 모드에서 '요청의 주인'을 준비하고 id 를 돌려준다.

    local 은 앱이 뜰 때 `id=1` 행을 만들어 두므로 로그인이 없다 (09-mode-matrix.md 3.4).
    cloud 는 동의와 키 등록까지 끝난 회원을 만들고 세션 쿠키를 심는다.
    """
    if mode == "local":
        return LOCAL_USER_ID
    user_id = make_cloud_user()
    login(client, user_id)
    return user_id
