"""애플리케이션 수명주기 동안 공유되는 의존성."""

from typing import Annotated

from fastapi import Depends, Request

from app.providers.base import LLMProvider
from app.services.analyzer import AnalyzerService
from app.services.practice import PracticeService


def get_provider(request: Request) -> LLMProvider:
    return request.app.state.provider


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
