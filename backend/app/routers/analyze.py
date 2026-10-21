import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.db import AnalysisRecord, PracticeRecord
from app.deps import ActiveUser, AnalyzerDep, DbDep, PracticeDep
from app.errors import LLMError
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AppConfigResponse,
    DoneEvent,
    HealthResponse,
    LLMHealth,
    PracticeRequest,
    PracticeResponse,
)
from app.services import records, usage
from app.services.analyzer import AnalyzerService

router = APIRouter(prefix="/api", tags=["analyze"])


API_KEY_ISSUE_URL = "https://aistudio.google.com/apikey"


@router.get("/config", response_model=AppConfigResponse)
def app_config() -> AppConfigResponse:
    """프론트가 로그인 화면을 띄울지, 바로 분석 화면을 띄울지 정하는 데 쓴다."""
    settings = get_settings()
    return AppConfigResponse(
        mode=settings.app_mode,
        requires_login=settings.is_cloud,
        model=settings.gemini_model if settings.is_cloud else settings.llm_model,
        daily_analysis_limit=settings.daily_analysis_limit if settings.is_cloud else 0,
        daily_practice_limit=settings.daily_practice_limit if settings.is_cloud else 0,
        api_key_issue_url=API_KEY_ISSUE_URL if settings.is_cloud else "",
        max_input_chars=settings.max_input_chars,
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """로컬 모드에서 llama-server 연결 상태를 알려준다.

    cloud 모드에서는 회원 키로만 호출할 수 있어 서버가 미리 확인할 것이 없다.
    키 유효성은 등록 시점에 한 번 확인한다(PUT /api/auth/api-key).
    """
    settings = get_settings()
    if settings.is_cloud:
        return HealthResponse(
            llm=LLMHealth(reachable=True, base_url=settings.gemini_base_url, models=[settings.gemini_model])
        )

    reachable, models, detail = await request.app.state.provider.health()
    return HealthResponse(
        llm=LLMHealth(
            reachable=reachable,
            base_url=settings.llm_base_url,
            models=models,
            detail=detail,
        )
    )


def _check_length(request: AnalyzeRequest) -> None:
    """모드별 입력 상한. 스키마의 절대 상한보다 좁다 (09-mode-matrix.md 3.1)."""
    limit = get_settings().max_input_chars
    if len(request.text) > limit:
        raise RequestValidationError(
            [
                {
                    "type": "string_too_long",
                    "loc": ("body", "text"),
                    "msg": f"String should have at most {limit} characters",
                    "input": request.text[:50],
                }
            ]
        )


def _charge_analysis(db, user) -> None:
    """호출 전에 한도를 확인하고 사용량을 올린다.

    회원 각자의 Gemini 한도를 쓰는 cloud 에서만 센다 (09-mode-matrix.md 3.3).
    실패한 호출도 한도를 소모하므로 성공 여부와 무관하게 먼저 센다.
    분석 한 번은 LLM 호출 네 번이다.
    """
    settings = get_settings()
    if not settings.is_cloud:
        return
    usage.check_and_increment(
        db, user, kind="analyses", limit=settings.daily_analysis_limit, llm_calls=4
    )


def _save_analysis(db, user, request: AnalyzeRequest, response: AnalyzeResponse) -> None:
    db.add(
        AnalysisRecord(
            user_id=user.id,
            source_text=request.text,
            level=request.level,
            result=records.stamp(response.result.model_dump()),
            markdown=response.markdown.model_dump(),
            failed_parts=response.meta.failed_parts,
            elapsed_ms=response.meta.elapsed_ms,
        )
    )
    db.commit()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest, analyzer: AnalyzerDep, db: DbDep, user: ActiveUser
) -> AnalyzeResponse:
    """네 파트를 모두 끝낸 뒤 한 번에 돌려준다."""
    _check_length(request)
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
    request: AnalyzeRequest, analyzer: AnalyzerDep, db: DbDep, user: ActiveUser
) -> StreamingResponse:
    """파트가 완성되는 대로 SSE 로 흘려보낸다.

    이벤트 종류: `part` · `part_error` · `done` · `error`.
    한 파트가 실패해도 나머지는 계속 진행하므로, 스트림은 항상 `done` 으로 끝난다
    (연결 불가·타임아웃처럼 이어가도 소용없는 경우는 제외).
    """
    _check_length(request)
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
    request: PracticeRequest, grader: PracticeDep, db: DbDep, user: ActiveUser
) -> PracticeResponse:
    """예문을 가린 채 학습자가 쓴 영어 문장을 채점한다."""
    settings = get_settings()
    if settings.is_cloud:
        usage.check_and_increment(
            db, user, kind="practices", limit=settings.daily_practice_limit
        )

    response = await grader.grade(request)

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
