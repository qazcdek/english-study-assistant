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
from app.errors import ApiKeyRequiredError, AuthRequiredError, ConsentRequiredError
from app.providers.base import LLMProvider
from app.providers.gemini import GeminiProvider
from app.services.analyzer import AnalyzerService
from app.services.practice import PracticeService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def db_session(settings: SettingsDep) -> Iterator[Session]:
    if not settings.is_cloud:
        raise RuntimeError("로컬 모드에는 DB 가 없습니다.")
    yield from get_session()


DbDep = Annotated[Session, Depends(db_session)]


def get_cipher(settings: SettingsDep) -> KeyCipher:
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


def ready_user(user: UserDep) -> User:
    """동의와 API 키 등록까지 끝난 회원만 통과시킨다."""
    if not user.has_consented:
        raise ConsentRequiredError()
    if not user.has_api_key:
        raise ApiKeyRequiredError()
    return user


ReadyUser = Annotated[User, Depends(ready_user)]


def maybe_db(settings: SettingsDep) -> Iterator[Session | None]:
    """cloud 면 세션을, 로컬이면 None. 두 모드를 함께 쓰는 라우터용."""
    if not settings.is_cloud:
        yield None
        return
    yield from get_session()


MaybeDb = Annotated[Session | None, Depends(maybe_db)]


def maybe_user(request: Request, settings: SettingsDep, db: MaybeDb) -> User | None:
    if not settings.is_cloud or db is None:
        return None
    return ready_user(current_user(request, settings, db))


MaybeUser = Annotated[User | None, Depends(maybe_user)]


async def get_provider(request: Request, settings: SettingsDep) -> AsyncIterator[LLMProvider]:
    """로컬은 공유 프로바이더, 웹은 회원 키로 만든 일회용 프로바이더."""
    if not settings.is_cloud:
        yield request.app.state.provider
        return

    # cloud: 회원 인증 → 키 복호화 → 요청 전용 프로바이더
    with next(get_session()) as db:  # type: ignore[arg-type]
        user = current_user(request, settings, db)
        user = ready_user(user)
        api_key = KeyCipher(settings.encryption_key).decrypt(user.encrypted_api_key or "")

    provider = GeminiProvider(
        api_key,
        base_url=settings.gemini_base_url,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
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
