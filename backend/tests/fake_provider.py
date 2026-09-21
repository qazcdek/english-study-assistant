"""llama-server 없이 테스트하기 위한 가짜 프로바이더.

분석이 파트별 호출로 나뉘었으므로, 프롬프트의 스키마를 보고 해당 파트의 응답을 돌려준다.
"""

import json
from typing import Any

from app.providers.base import ChatMessage, CompletionResult, LLMProvider

PART_PAYLOADS: dict[str, dict] = {
    "translation": {
        "translation": "이 영국식 표현은 최근 미국 주식시장의 회복력을 완벽하게 요약해 준다."
    },
    "expressions": {
        "expressions": [
            {
                "expression": "across the pond",
                "type": "관용구",
                "meaning": "(비격식) 대서양을 건너 — 주로 영국과 미국 사이를 가리킬 때 쓴다.",
                "example": "Her book finally made it across the pond.",
                "example_ko": "그녀의 책은 마침내 대서양을 건너갔다.",
            },
            {
                "expression": "sum up",
                "type": "Phrasal Verb",
                "meaning": "요약하다, 진수를 보여주다",
            },
        ]
    },
    "structures": {
        "structures": [
            {
                "fragment": "It's unlikely to find its way...",
                "explanation": "be unlikely to 는 '~할 것 같지 않다'라는 뜻으로 가능성이 낮음을 나타낸다.",
            }
        ]
    },
    "overview": {
        "overview": {
            "domain": "경제·금융 시사 논평",
            "tone": "가볍게 비꼬는 분석적 어조",
            "formality": "격식",
            "style": "문어체",
            "key_expressions": ["across the pond"],
            "comment": "칼럼에서 비유적으로 자주 쓰인다. 격식 있는 글에서 써먹기 좋다.",
        }
    },
}


PRACTICE_PAYLOAD = {
    "verdict": "통함",
    "uses_target": True,
    "good_point": "make it across 를 목표 표현 그대로 살려 썼다.",
    "target_note": "across the pond 를 바르게 썼다. 다만 시제가 제시문과 어긋난다.",
    "corrected": "Her novel finally made it across the pond.",
    "other_notes": ["novel 앞에 소유격이 빠졌다.", "문장 끝 마침표가 없다.", "세 번째 지적"],
}


def field_of(json_schema: dict[str, Any] | None) -> str:
    """파트 스키마의 최상위 키가 곧 파트 이름이다. 연습 채점은 'practice' 로 구분한다."""
    if not json_schema:
        return ""
    props = json_schema.get("properties", {})
    if "verdict" in props:
        return "practice"
    return next(iter(props), "")


class FakeProvider(LLMProvider):
    """기본은 모든 파트를 정상 응답한다.

    `overrides` 로 특정 파트만 다른 응답을 주도록 바꿀 수 있다.
    값이 리스트면 그 파트의 호출 순서대로 하나씩 쓴다 (재시도 테스트용).
    """

    def __init__(self, overrides: dict[str, str | list[str]] | None = None) -> None:
        self.overrides = overrides or {}
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> CompletionResult:
        field = field_of(json_schema)
        seen = sum(1 for f, _ in self.calls if f == field)
        self.calls.append((field, messages))

        override = self.overrides.get(field)
        if isinstance(override, list):
            text = override[min(seen, len(override) - 1)]
        elif isinstance(override, str):
            text = override
        elif field == "practice":
            text = json.dumps(PRACTICE_PAYLOAD, ensure_ascii=False)
        else:
            text = json.dumps(PART_PAYLOADS[field], ensure_ascii=False)

        return CompletionResult(text=text, model="fake-model")

    async def health(self) -> tuple[bool, list[str], str | None]:
        return True, ["fake-model"], None
