"""요청마다 필요한 의존성.

로컬 모드와 웹 배포 모드의 차이가 여기에 모인다.

- 로컬: 로그인이 없고, 앱 시작 시 만든 llama-server 프로바이더 하나를 공유한다.
- 웹  : 로그인한 회원의 Gemini 키로 **요청마다** 프로바이더를 새로 만든다.
        키는 회원의 것이고 그 사람의 사용 한도가 소모되므로 공유하면 안 된다.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.crypto import KeyCipher
from app.auth.session import COOKIE_NAME, read_token
from app.config import Settings, get_settings
from app.db import User, get_session
from app.errors import (
    ApiKeyRequiredError,
    AppError,
    AuthRequiredError,
    ConsentRequiredError,
)
from app.providers import registry
from app.providers.base import LLMProvider
from app.services import keys
from app.services.analyzer import AnalyzerService
from app.services.practice import PracticeService

SettingsDep = Annotated[Settings, Depends(get_settings)]


# 로그인이 없는 로컬 모드에서 모든 기록을 매다는 사용자 행.
LOCAL_USER_ID = 1


def db_session() -> Iterator[Session]:
    """두 모드 모두 DB 를 쓴다. local 은 docker Postgres, cloud 는 Neon."""
    yield from get_session()


DbDep = Annotated[Session, Depends(db_session)]


def get_cipher(settings: SettingsDep) -> KeyCipher:
    """회원 키를 암호화하는 도구.

    **로컬에도 필요해졌다.** 전에는 로컬이 키를 저장한 적이 없어서 `ENCRYPTION_KEY`
    가 cloud 전용이었다. 이제 로컬에서도 cloud LLM 을 고를 수 있으므로(M12-T1)
    그 키를 보관해야 하고, 보관한다면 **암호화해야 한다.**

    다만 **llama-server 만 쓰는 로컬에는 여전히 필요 없다.** 그래서 설정을 항상
    요구하지 않고, 실제로 키를 저장하려 할 때 안내한다 — 안 그러면 모델 서버만
    쓰려는 사람이 쓸 일 없는 값을 만들어야 한다.
    """
    if not settings.encryption_key:
        raise AppError(
            "키를 암호화할 ENCRYPTION_KEY 가 없습니다. backend/.env 에 넣어 주세요 — "
            'python -c "from cryptography.fernet import Fernet;'
            'print(Fernet.generate_key().decode())"'
        )
    return KeyCipher(settings.encryption_key)


CipherDep = Annotated[KeyCipher, Depends(get_cipher)]


def current_user(request: Request, settings: SettingsDep, db: DbDep) -> User:
    """로그인한 회원. 없으면 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise AuthRequiredError()
    user_id = read_token(token, settings.session_secret)
    if user_id is None:
        raise AuthRequiredError("세션이 만료되었습니다. 다시 로그인해 주세요.")
    user = db.get(User, user_id)
    if user is None:
        raise AuthRequiredError()
    return user


UserDep = Annotated[User, Depends(current_user)]


def ready_user(user: UserDep, db: DbDep, settings: SettingsDep) -> User:
    """동의와 **활성 제공자의** 키 등록까지 끝난 회원만 통과시킨다.

    키를 제공자마다 따로 두므로(M12-T2) "키가 있다" 는 더 이상 회원 단위 사실이
    아니다. **지금 고른 제공자**의 키를 본다 — 다른 제공자 키가 있어도 지금 쓸
    제공자의 것이 없으면 호출할 수 없다.
    """
    if not user.has_consented:
        raise ConsentRequiredError()
    if not keys.has_key(db, user, keys.resolve(user, settings.app_mode)):
        raise ApiKeyRequiredError()
    return user


ReadyUser = Annotated[User, Depends(ready_user)]


def _local_user(db: Session) -> User:
    user = db.get(User, LOCAL_USER_ID)
    if user is None:  # pragma: no cover - 시작할 때 만든다
        raise RuntimeError("로컬 사용자 행이 없습니다. 앱을 다시 시작하세요.")
    return user


def session_user(request: Request, settings: SettingsDep, db: DbDep) -> User:
    """지금 요청의 주인. **신원만** 확인한다.

    저장된 기록을 읽고 지우는 데에는 동의나 API 키가 필요 없다.
    그것들은 LLM 을 부를 때 필요한 것이다.
    """
    if not settings.is_cloud:
        return _local_user(db)
    return current_user(request, settings, db)


def active_user(request: Request, settings: SettingsDep, db: DbDep) -> User:
    """LLM 을 부를 수 있는 상태인 주인.

    cloud 는 이용 동의와 API 키 등록까지 끝나야 한다. local 은 그런 관문이 없다.
    """
    if not settings.is_cloud:
        return _local_user(db)
    return ready_user(current_user(request, settings, db), db, settings)


SessionUser = Annotated[User, Depends(session_user)]
ActiveUser = Annotated[User, Depends(active_user)]


async def get_provider(request: Request, settings: SettingsDep) -> AsyncIterator[LLMProvider]:
    """회원이 고른 제공자로 만든다.

    **llama-server 만 공유한다** — 내 PC 의 서버 하나이고 키가 없다. cloud LLM 은
    회원 키로 호출하므로 **요청마다 새로** 만든다. 공유하면 다른 회원의 키로
    호출된다 (09 §3.2).
    """
    with next(get_session()) as db:  # type: ignore[arg-type]
        user = session_user(request, settings, db)
        if settings.is_cloud:
            user = ready_user(user, db, settings)
        choice = keys.resolve(user, settings.app_mode)
        api_key = (
            keys.decrypt(db, user.id, choice.provider.id, KeyCipher(settings.encryption_key))
            if choice.provider.needs_key
            else ""
        )

    if choice.provider.id == registry.LLAMA:
        # 앱이 뜰 때 만든 것을 그대로 쓴다. 키가 없으니 회원마다 다를 것이 없다.
        yield request.app.state.provider
        return

    provider = registry.build(choice.provider.id, choice.model, api_key, settings)
    try:
        yield provider
    finally:
        await provider.aclose()


ProviderDep = Annotated[LLMProvider, Depends(get_provider)]


def get_analyzer(provider: ProviderDep) -> AnalyzerService:
    return AnalyzerService(provider)


def get_practice(provider: ProviderDep) -> PracticeService:
    return PracticeService(provider)


AnalyzerDep = Annotated[AnalyzerService, Depends(get_analyzer)]
PracticeDep = Annotated[PracticeService, Depends(get_practice)]
