"""분석 오케스트레이션.

분석을 네 파트(번역 / 표현 / 구조 / 총평)로 쪼개 각각 독립된 LLM 호출로 처리한다.

이렇게 나눈 이유:
- 파트마다 JSON 스키마가 작아 모델이 형식을 지키기 쉽다.
- 한 파트가 실패해도 나머지는 살아남는다 (전체 502 대신 부분 결과).
- 완성된 순서대로 흘려보낼 수 있어, 총 시간이 조금 늘어도 체감이 빠르다.

총평은 표현 목록에 의존하므로(`key_expressions` 가 표의 값과 일치해야 한다)
파트는 정의된 순서대로 직렬 실행한다.
"""

import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError

from app.errors import LLMBadOutputError, LLMError, LLMTruncatedError
from app.prompts.analysis import PART_SPECS, PartSpec, build_messages
from app.providers.base import LLMProvider
from app.schemas import (
    AnalysisResult,
    AnalyzeMeta,
    AnalyzeRequest,
    AnalyzeResponse,
    DoneEvent,
    PartErrorEvent,
    PartEvent,
)
from app.services import markdown

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def extract_json(text: str) -> dict:
    """모델이 덧붙인 코드 펜스나 앞뒤 잡담을 걷어내고 JSON 객체를 꺼낸다."""
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("응답에서 JSON 객체를 찾지 못했습니다.")
    return json.loads(cleaned[start : end + 1])


class AnalyzerService:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    # ------------------------------------------------------------------ 파트 실행

    async def _run_part(
        self, spec: PartSpec, request: AnalyzeRequest, state: dict[str, Any]
    ) -> tuple[Any, str, bool]:
        """한 파트를 실행해 (값, 모델명, 재시도 여부) 를 돌려준다.

        형식이 어긋나면 temperature 0 으로 한 번 더 시도한다.
        `max_tokens` 에서 잘린 경우는 재시도해도 같은 결과이므로 곧장 올려보낸다.
        """
        last_error: Exception | None = None
        last_raw = ""
        model = ""

        for attempt in range(2):
            retry = attempt > 0
            completion = await self.provider.complete(
                build_messages(spec, request.text, request.level, state, retry=retry),
                temperature=0.0 if retry else None,
                json_schema=spec.schema,
            )
            model = completion.model
            last_raw = completion.text

            try:
                part = spec.model.model_validate(extract_json(completion.text))
            except (ValueError, ValidationError) as exc:
                last_error = exc
                continue

            return getattr(part, spec.field), model, retry

        raise LLMBadOutputError(
            f"[{spec.title}] {last_error} / 원본 응답 앞부분: {last_raw[:200]}"
        )

    # ------------------------------------------------------------------ 스트리밍

    async def stream(self, request: AnalyzeRequest) -> AsyncIterator[PartEvent | PartErrorEvent | DoneEvent]:
        started = time.perf_counter()
        state: dict[str, Any] = {}
        model = ""
        retried: list[str] = []
        total = len(PART_SPECS)

        for index, spec in enumerate(PART_SPECS):
            part_started = time.perf_counter()
            try:
                value, model, was_retried = await self._run_part(spec, request, state)
            except LLMError as exc:
                yield PartErrorEvent(
                    field=spec.field,
                    title=spec.title,
                    index=index,
                    total=total,
                    code=exc.code,
                    message=exc.message,
                    detail=exc.detail or None,
                )
                # 연결 불가·타임아웃이면 남은 파트도 어차피 실패한다.
                if not isinstance(exc, (LLMBadOutputError, LLMTruncatedError)):
                    break
                continue

            if was_retried:
                retried.append(spec.field)

            # 총평 프롬프트가 표현 목록을 참조하므로 원본 형태로도 남겨 둔다.
            state[spec.field] = (
                [v.model_dump() for v in value] if isinstance(value, list) else value
            )

            yield PartEvent(
                field=spec.field,
                title=spec.title,
                index=index,
                total=total,
                data={spec.field: _dump(value)},
                markdown=markdown.render_part(spec.field, value),
                elapsed_ms=int((time.perf_counter() - part_started) * 1000),
                retried=was_retried,
            )

        result = self._build_result(request, state)
        yield DoneEvent(
            result=result,
            markdown=markdown.render(result),
            meta=AnalyzeMeta(
                model=model or "unknown",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                retried_parts=retried,
                # 실패한 파트 + 앞선 실패로 아예 시도하지 못한 파트
                failed_parts=[s.field for s in PART_SPECS if s.field not in state],
            ),
        )

    # ------------------------------------------------------------------ 일괄 실행

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """스트림을 모아 한 번에 돌려준다. 모든 파트가 실패하면 에러를 올린다."""
        done: DoneEvent | None = None
        first_error: PartErrorEvent | None = None

        async for event in self.stream(request):
            if isinstance(event, PartErrorEvent) and first_error is None:
                first_error = event
            elif isinstance(event, DoneEvent):
                done = event

        assert done is not None  # stream 은 항상 DoneEvent 로 끝난다
        if len(done.meta.failed_parts) == len(PART_SPECS) and first_error is not None:
            raise LLMBadOutputError(first_error.detail or first_error.message)

        return AnalyzeResponse(result=done.result, markdown=done.markdown, meta=done.meta)

    # ------------------------------------------------------------------ 내부

    @staticmethod
    def _build_result(request: AnalyzeRequest, state: dict[str, Any]) -> AnalysisResult:
        return AnalysisResult.model_validate({"source_text": request.text, **state})


def _dump(value: Any) -> Any:
    if isinstance(value, list):
        return [v.model_dump() for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value
