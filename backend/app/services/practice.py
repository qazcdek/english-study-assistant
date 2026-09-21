"""작문 연습 채점 서비스."""

import time

from pydantic import ValidationError

from app.errors import LLMBadOutputError
from app.prompts import practice as prompts
from app.providers.base import LLMProvider
from app.schemas import AnalyzeMeta, PracticeRequest, PracticeResponse, PracticeResult
from app.services.analyzer import extract_json

MAX_OTHER_NOTES = 2


class PracticeService:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def grade(self, request: PracticeRequest) -> PracticeResponse:
        started = time.perf_counter()
        last_error: Exception | None = None
        last_raw = ""
        model = ""
        retried: list[str] = []

        for attempt in range(2):
            retry = attempt > 0
            completion = await self.provider.complete(
                prompts.build_messages(
                    expression=request.expression,
                    meaning=request.meaning,
                    prompt_ko=request.prompt_ko,
                    model_answer=request.model_answer,
                    learner_answer=request.learner_answer,
                    level=request.level,
                    retry=retry,
                ),
                temperature=0.0 if retry else None,
                json_schema=prompts.PRACTICE_JSON_SCHEMA,
            )
            model = completion.model
            last_raw = completion.text

            try:
                result = PracticeResult.model_validate(extract_json(completion.text))
            except (ValueError, ValidationError) as exc:
                last_error = exc
                continue

            if retry:
                retried.append("practice")

            # 지적이 쏟아지면 학습자가 압도된다. 프롬프트로 막고 코드로도 자른다.
            result.other_notes = [n for n in result.other_notes if n.strip()][:MAX_OTHER_NOTES]
            if result.corrected.strip() == request.learner_answer.strip():
                result.corrected = ""

            return PracticeResponse(
                result=result,
                model_answer=request.model_answer,
                meta=AnalyzeMeta(
                    model=model,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    retried_parts=retried,
                ),
            )

        raise LLMBadOutputError(f"{last_error} / 원본 응답 앞부분: {last_raw[:200]}")
