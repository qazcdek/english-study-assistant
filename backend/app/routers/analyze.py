import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.db import AnalysisRecord, PracticeRecord
from app.deps import AnalyzerDep, MaybeDb, MaybeUser, PracticeDep, ProviderDep
from app.errors import LLMError
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DoneEvent,
    HealthResponse,
    LLMHealth,
    PracticeRequest,
    PracticeResponse,
)
from app.services import usage
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


def _charge_analysis(db, user) -> None:
    """호출 전에 한도를 확인하고 사용량을 올린다.

    실패한 호출도 회원의 Gemini 한도를 소모하므로 성공 여부와 무관하게 먼저 센다.
    분석 한 번은 LLM 호출 네 번이다.
    """
    if db is None or user is None:
        return
    usage.check_and_increment(
        db, user, kind="analyses", limit=get_settings().daily_analysis_limit, llm_calls=4
    )


def _save_analysis(db, user, request: AnalyzeRequest, response: AnalyzeResponse) -> None:
    if db is None or user is None:
        return
    db.add(
        AnalysisRecord(
            user_id=user.id,
            source_text=request.text,
            level=request.level,
            result=response.result.model_dump(),
            markdown=response.markdown.model_dump(),
            failed_parts=response.meta.failed_parts,
            elapsed_ms=response.meta.elapsed_ms,
        )
    )
    db.commit()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest, analyzer: AnalyzerDep, db: MaybeDb, user: MaybeUser
) -> AnalyzeResponse:
    """네 파트를 모두 끝낸 뒤 한 번에 돌려준다."""
    _charge_analysis(db, user)
    response = await analyzer.analyze(request)
    _save_analysis(db, user, request, response)
    return response


async def _sse(
    analyzer: AnalyzerService, request: AnalyzeRequest, db, user
) -> AsyncIterator[str]:
    try:
        async for event in analyzer.stream(request):
            if isinstance(event, DoneEvent):
                _save_analysis(
                    db,
                    user,
                    request,
                    AnalyzeResponse(
                        result=event.result, markdown=event.markdown, meta=event.meta
                    ),
                )
            yield f"data: {event.model_dump_json()}\n\n"
    except LLMError as exc:
        payload = {"type": "error", "code": exc.code, "message": exc.message, "detail": exc.detail}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/analyze/stream")
async def analyze_stream(
    request: AnalyzeRequest, analyzer: AnalyzerDep, db: MaybeDb, user: MaybeUser
) -> StreamingResponse:
    """파트가 완성되는 대로 SSE 로 흘려보낸다.

    이벤트 종류: `part` · `part_error` · `done` · `error`.
    한 파트가 실패해도 나머지는 계속 진행하므로, 스트림은 항상 `done` 으로 끝난다
    (연결 불가·타임아웃처럼 이어가도 소용없는 경우는 제외).
    """
    _charge_analysis(db, user)
    return StreamingResponse(
        _sse(analyzer, request, db, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 역방향 프록시의 버퍼링 방지
        },
    )


@router.post("/practice", response_model=PracticeResponse)
async def practice(
    request: PracticeRequest, grader: PracticeDep, db: MaybeDb, user: MaybeUser
) -> PracticeResponse:
    """예문을 가린 채 학습자가 쓴 영어 문장을 채점한다."""
    if db is not None and user is not None:
        usage.check_and_increment(
            db, user, kind="practices", limit=get_settings().daily_practice_limit
        )

    response = await grader.grade(request)

    if db is not None and user is not None:
        db.add(
            PracticeRecord(
                user_id=user.id,
                expression=request.expression,
                prompt_ko=request.prompt_ko,
                model_answer=request.model_answer,
                learner_answer=request.learner_answer,
                verdict=response.result.verdict,
                uses_target=response.result.uses_target,
                feedback=response.result.model_dump(),
            )
        )
        db.commit()

    return response
