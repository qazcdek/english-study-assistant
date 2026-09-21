import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.deps import AnalyzerDep, PracticeDep, ProviderDep
from app.errors import LLMError
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthResponse,
    LLMHealth,
    PracticeRequest,
    PracticeResponse,
)
from app.services.analyzer import AnalyzerService

router = APIRouter(prefix="/api", tags=["analyze"])


@router.get("/health", response_model=HealthResponse)
async def health(provider: ProviderDep) -> HealthResponse:
    """백엔드는 살아 있다는 전제로, llama-server 연결 상태를 함께 알려준다."""
    settings = get_settings()
    reachable, models, detail = await provider.health()
    return HealthResponse(
        llm=LLMHealth(
            reachable=reachable,
            base_url=settings.llm_base_url,
            models=models,
            detail=detail,
        )
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, analyzer: AnalyzerDep) -> AnalyzeResponse:
    """네 파트를 모두 끝낸 뒤 한 번에 돌려준다."""
    return await analyzer.analyze(request)


async def _sse(analyzer: AnalyzerService, request: AnalyzeRequest) -> AsyncIterator[str]:
    try:
        async for event in analyzer.stream(request):
            yield f"data: {event.model_dump_json()}\n\n"
    except LLMError as exc:
        payload = {"type": "error", "code": exc.code, "message": exc.message, "detail": exc.detail}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/analyze/stream")
async def analyze_stream(request: AnalyzeRequest, analyzer: AnalyzerDep) -> StreamingResponse:
    """파트가 완성되는 대로 SSE 로 흘려보낸다.

    이벤트 종류: `part` · `part_error` · `done` · `error`.
    한 파트가 실패해도 나머지는 계속 진행하므로, 스트림은 항상 `done` 으로 끝난다
    (연결 불가·타임아웃처럼 이어가도 소용없는 경우는 제외).
    """
    return StreamingResponse(
        _sse(analyzer, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 역방향 프록시의 버퍼링 방지
        },
    )


@router.post("/practice", response_model=PracticeResponse)
async def practice(request: PracticeRequest, grader: PracticeDep) -> PracticeResponse:
    """예문을 가린 채 학습자가 쓴 영어 문장을 채점한다."""
    return await grader.grade(request)
