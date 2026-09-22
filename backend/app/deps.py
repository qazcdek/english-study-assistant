"""요청마다 필요한 의존성."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import User, get_session
from app.providers.base import LLMProvider
from app.services.analyzer import AnalyzerService
from app.services.practice import PracticeService

# 혼자 쓰는 도구라 로그인이 없다. 시작할 때 만들어 둔 행 하나를 계속 쓴다.
LOCAL_USER_ID = 1


def get_provider(request: Request) -> LLMProvider:
    return request.app.state.provider


def db_session() -> Iterator[Session]:
    yield from get_session()


DbDep = Annotated[Session, Depends(db_session)]


def current_user(db: DbDep) -> User:
    user = db.get(User, LOCAL_USER_ID)
    if user is None:  # pragma: no cover - 시작 시 만들어 둔다
        raise RuntimeError("로컬 사용자 행이 없습니다. 앱을 다시 시작하세요.")
    return user


UserDep = Annotated[User, Depends(current_user)]


def get_analyzer(
    provider: Annotated[LLMProvider, Depends(get_provider)],
) -> AnalyzerService:
    return AnalyzerService(provider)


def get_practice(
    provider: Annotated[LLMProvider, Depends(get_provider)],
) -> PracticeService:
    return PracticeService(provider)


ProviderDep = Annotated[LLMProvider, Depends(get_provider)]
AnalyzerDep = Annotated[AnalyzerService, Depends(get_analyzer)]
PracticeDep = Annotated[PracticeService, Depends(get_practice)]
