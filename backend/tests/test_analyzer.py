import json

import pytest

from app.errors import LLMBadOutputError, LLMUnavailableError
from app.prompts.analysis import PART_FIELDS
from app.providers.base import ChatMessage, CompletionResult, LLMProvider
from app.schemas import AnalyzeRequest, DoneEvent, PartErrorEvent, PartEvent
from app.services.analyzer import AnalyzerService, extract_json
from tests.fake_provider import PART_PAYLOADS, FakeProvider


def test_extract_json_strips_code_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_finds_object_in_chatter():
    assert extract_json('알겠습니다! {"a": 1} 이렇게 나왔습니다.') == {"a": 1}


async def collect(service, text="It's unlikely to find its way across the pond."):
    return [e async for e in service.stream(AnalyzeRequest(text=text))]


# --------------------------------------------------------------------- 스트리밍


async def test_stream_emits_one_event_per_part_then_done():
    events = await collect(AnalyzerService(FakeProvider()))

    parts = [e for e in events if isinstance(e, PartEvent)]
    assert [p.field for p in parts] == list(PART_FIELDS)
    assert [p.index for p in parts] == [0, 1, 2, 3]
    assert all(p.total == 4 for p in parts)
    assert isinstance(events[-1], DoneEvent)


async def test_part_events_carry_rendered_markdown():
    events = await collect(AnalyzerService(FakeProvider()))
    by_field = {e.field: e for e in events if isinstance(e, PartEvent)}

    assert by_field["translation"].markdown.startswith("### 자연스러운 번역")
    assert "| 표현 (영어) | 유형 | 의미 및 설명 | 예문 |" in by_field["expressions"].markdown
    assert "**꼭 챙길 표현**: `across the pond`" in by_field["overview"].markdown


async def test_overview_prompt_receives_expressions_from_earlier_part():
    """총평의 key_expressions 가 표의 값과 맞으려면 표현 목록이 전달되어야 한다."""
    provider = FakeProvider()
    await collect(AnalyzerService(provider))

    overview_prompt = next(m[1].content for f, m in provider.calls if f == "overview")
    assert "across the pond" in overview_prompt
    assert "sum up" in overview_prompt


async def test_done_event_assembles_full_result():
    events = await collect(AnalyzerService(FakeProvider()))
    done = events[-1]

    assert done.result.translation.startswith("이 영국식")
    assert len(done.result.expressions) == 2
    assert done.result.overview.domain == "경제·금융 시사 논평"
    assert done.meta.failed_parts == []
    assert done.markdown.full.count("---\n\n###") == 3


# --------------------------------------------------------------------- 실패 격리


async def test_one_bad_part_does_not_sink_the_others():
    service = AnalyzerService(FakeProvider({"structures": "형식이 틀린 응답"}))
    events = await collect(service)

    errors = [e for e in events if isinstance(e, PartErrorEvent)]
    assert [e.field for e in errors] == ["structures"]

    done = events[-1]
    assert done.meta.failed_parts == ["structures"]
    assert done.result.translation  # 다른 파트는 살아남는다
    assert done.result.overview is not None
    assert "_특별히 설명할 구문이 없습니다._" in done.markdown.structures


async def test_part_retries_once_before_failing():
    good = json.dumps(PART_PAYLOADS["expressions"], ensure_ascii=False)
    service = AnalyzerService(FakeProvider({"expressions": ["깨진 응답", good]}))
    events = await collect(service)

    assert not [e for e in events if isinstance(e, PartErrorEvent)]
    assert events[-1].meta.retried_parts == ["expressions"]


async def test_connection_failure_stops_remaining_parts():
    """연결이 끊겼으면 남은 파트를 시도해 봐야 소용없다."""

    class DeadProvider(LLMProvider):
        async def complete(self, messages, **kwargs) -> CompletionResult:
            raise LLMUnavailableError("connection refused")

        async def health(self):
            return False, [], "down"

    events = await collect(AnalyzerService(DeadProvider()))
    errors = [e for e in events if isinstance(e, PartErrorEvent)]

    assert [e.field for e in errors] == ["translation"]  # 첫 파트에서 멈춘다
    assert events[-1].meta.failed_parts == list(PART_FIELDS)


# --------------------------------------------------------------------- 일괄 실행


async def test_analyze_collects_stream():
    response = await AnalyzerService(FakeProvider()).analyze(AnalyzeRequest(text="hello"))

    assert response.result.source_text == "hello"
    assert response.meta.failed_parts == []
    assert response.markdown.full.startswith("### 자연스러운 번역")


async def test_analyze_raises_when_every_part_fails():
    broken = dict.fromkeys(PART_FIELDS, "전부 깨진 응답")
    service = AnalyzerService(FakeProvider(broken))

    with pytest.raises(LLMBadOutputError):
        await service.analyze(AnalyzeRequest(text="hello"))


def test_chat_message_shape():
    assert ChatMessage(role="user", content="x").to_dict() == {"role": "user", "content": "x"}


async def test_structures_prompt_lists_already_covered_expressions():
    """어휘 항목이 구조 해설로 새는 것을 막기 위해 앞 파트의 결과를 넘긴다."""
    provider = FakeProvider()
    await collect(AnalyzerService(provider))

    prompt = next(m[1].content for f, m in provider.calls if f == "structures")
    assert "이미 다룬 표현:" in prompt
    assert "across the pond" in prompt
    assert "sum up" in prompt


def test_expression_count_limits_follow_level():
    """개수는 프롬프트 문구가 아니라 스키마로 강제한다. 작은 모델이 하한을 목표로 삼기 때문이다."""
    from app.prompts.analysis import PART_SPECS

    spec = next(s for s in PART_SPECS if s.field == "expressions")
    counts = {
        level: (
            spec.schema_for(level)["properties"]["expressions"]["minItems"],
            spec.schema_for(level)["properties"]["expressions"]["maxItems"],
        )
        for level in ("beginner", "intermediate", "advanced")
    }

    assert counts == {"beginner": (3, 5), "intermediate": (6, 8), "advanced": (7, 10)}
    # 원본 스키마는 건드리지 않는다
    assert "minItems" not in spec.schema["properties"]["expressions"]


def test_key_expressions_are_capped_at_three():
    """'특히 챙길 것'이라는 선별의 뜻이 살려면 목록 전체를 옮겨 적으면 안 된다."""
    from app.prompts.analysis import PART_SPECS

    spec = next(s for s in PART_SPECS if s.field == "overview")
    key = spec.schema["properties"]["overview"]["properties"]["key_expressions"]

    assert (key["minItems"], key["maxItems"]) == (1, 3)


async def test_analyzer_sends_level_specific_schema():
    provider = FakeProvider()
    service = AnalyzerService(provider)
    [e async for e in service.stream(AnalyzeRequest(text="hello", level="advanced"))]

    # FakeProvider 가 파트를 스키마로 구분하므로, 호출이 제대로 갈렸다면 네 파트 모두 기록된다
    assert [f for f, _ in provider.calls] == list(PART_FIELDS)
