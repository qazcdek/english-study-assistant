import json

import pytest

from app.errors import LLMBadOutputError, LLMUnavailableError
from app.prompts.analysis import PART_FIELDS
from app.providers.base import ChatMessage, CompletionResult, LLMProvider
from app.providers.schema import SchemaLimits
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
    # 표에는 **중급 하나만** 넣는다 (M16) — 셋을 칸 셋으로 벌리면 표가 좁아 깨진다.
    assert "| 표현 (영어) | 유형 | 의미 및 설명 | 예문 (중급) |" in by_field["expressions"].markdown
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


def test_the_expression_cap_is_one_number_and_the_floor_follows_length():
    """개수는 프롬프트 문구가 아니라 스키마로 강제한다. 작은 모델이 하한을 목표로 삼기 때문이다.

    **상한은 하나다** (`M16`) — 난이도가 사라져 초급만 5개이던 분기가 없어졌다.
    """
    from app.prompts.analysis import PART_SPECS

    spec = next(s for s in PART_SPECS if s.field == "expressions")

    def limits(length):
        a = spec.schema_for(length)["properties"]["expressions"]
        return a["minItems"], a["maxItems"]

    assert limits(800)[1] == 8
    assert limits(150)[1] == 8  # 글이 짧아도 상한은 같다
    # 하한은 글 길이를 따른다
    assert limits(150)[0] == 1
    assert limits(800)[0] == 3
    # 원본 스키마는 건드리지 않는다
    assert "minItems" not in spec.schema["properties"]["expressions"]


def test_expression_floor_scales_with_text_length():
    """짧은 글에 억지로 개수를 채우게 하면 다어절 표현을 낱개로 쪼개거나 쉬운 낱말을 끌어온다."""
    from app.prompts.analysis import min_expressions

    assert min_expressions(0, 8) == 1
    assert min_expressions(199, 8) == 1
    assert min_expressions(200, 8) == 1
    assert min_expressions(400, 8) == 2
    assert min_expressions(600, 8) == 3


def test_expression_floor_never_exceeds_three():
    """하한이 높으면 모델이 규칙을 어겨서라도 숫자를 맞춘다. 고급은 다어절만 고르므로 특히 위험하다."""
    from app.prompts.analysis import MAX_MIN_EXPRESSIONS, min_expressions

    assert MAX_MIN_EXPRESSIONS == 3
    assert min_expressions(800, 8) == 3
    assert min_expressions(2000, 8) == 3
    assert min_expressions(100000, 8) == 3


def test_key_expressions_are_capped_at_three():
    """'특히 챙길 것'이라는 선별의 뜻이 살려면 목록 전체를 옮겨 적으면 안 된다."""
    from app.prompts.analysis import PART_SPECS

    spec = next(s for s in PART_SPECS if s.field == "overview")
    key = spec.schema["properties"]["overview"]["properties"]["key_expressions"]

    assert (key["minItems"], key["maxItems"]) == (1, 3)


async def test_the_analyzer_calls_every_part_once():
    provider = FakeProvider()
    service = AnalyzerService(provider)
    [e async for e in service.stream(AnalyzeRequest(text="hello"))]

    # FakeProvider 가 파트를 스키마로 구분하므로, 호출이 제대로 갈렸다면 네 파트 모두 기록된다
    assert [f for f, _ in provider.calls] == list(PART_FIELDS)


async def test_structure_markdown_keeps_all_four_parts():
    """한 필드에 몰아넣으면 구조 이름만 대고 끝나므로 조각을 나눠 받는다."""
    service = AnalyzerService(FakeProvider())
    events = await collect(service)
    md = next(e for e in events if isinstance(e, PartEvent) and e.field == "structures").markdown

    assert "**It's unlikely to find its way** — 형식주어 it 구문" in md
    assert "실제 주어는 뒤의 to부정사구다" in md
    assert "쉽게 쓰면: `The chance that it will spread is low`" in md
    assert "주의: 한국어에는 형식주어가 없어" in md


def test_the_request_has_no_level_to_send():
    """**분석에서 난이도를 걷어냈다** (`M16`). 보낼 칸이 없으면 되살아나지 않는다."""
    from app.schemas import AnalyzeRequest as Req

    assert "level" not in Req.model_fields


def test_the_system_prompt_has_no_level_guide_slot():
    """`08 §1` 이 적어 둔 문제다 — "깊게"·"최소한으로" 는 모델도 우리도 기준을 모른다.
    **자리를 없애야** 다시 안 들어온다."""
    from app.prompts.analysis import SHARED_SYSTEM

    assert "{level_guide}" not in SHARED_SYSTEM
    assert "level" not in SHARED_SYSTEM


def test_no_part_tells_the_model_what_level_the_learner_is():
    """**조립된 프롬프트를 본다.** 틀에서 자리를 없애도 파트 지시에 다시 적을 수 있다 —
    실제로 그 구멍을 깨뜨려 보고 알았다.

    분석의 깊이를 난이도로 말하는 어휘를 전부 막는다. 예문 규칙은 `beginner` 같은
    **칸 이름**으로만 난이도를 말하므로 걸리지 않는다.
    """
    from app.prompts.analysis import PART_SPECS, build_messages

    banned = ("학습자는 초급", "학습자는 중급", "학습자는 상급", "설명을 깊게", "난이도가 높")
    for spec in PART_SPECS:
        system = build_messages(spec, "hello world")[0].content
        for word in banned:
            assert word not in system, f"{spec.field} 에 '{word}' 가 들어왔다"


# --------------------------------------------------------------------- 예문 난이도


def expressions_spec():
    from app.prompts.analysis import PART_SPECS

    return next(s for s in PART_SPECS if s.field == "expressions")


def expression_item():
    return expressions_spec().schema_for(400)["properties"]["expressions"]["items"]


def test_nuance_is_always_there_now():
    """초급 스키마에서 `nuance` 를 빼던 분기가 사라졌다 — 중급 모양이 유일하다."""
    item = expression_item()

    assert "nuance" in item["properties"]
    assert "nuance" in item["required"]
    assert item["additionalProperties"] is False


def test_all_three_difficulties_are_required():
    """**선택으로 두고 프롬프트로 부탁하면 작은 모델이 생략을 기본값으로 삼는다**
    (H-019 · H-021). 하나라도 비면 그 난이도로 연습할 수 없다."""
    examples = expression_item()["properties"]["examples"]

    assert set(examples["properties"]) == {"beginner", "intermediate", "advanced"}
    assert set(examples["required"]) == {"beginner", "intermediate", "advanced"}
    assert examples["additionalProperties"] is False
    for name, pair in examples["properties"].items():
        assert set(pair["required"]) == {"en", "ko"}, name
        assert pair["additionalProperties"] is False, name


def test_the_old_single_example_slot_is_gone():
    """`example`/`example_ko` 를 남겨 두면 모델이 그 쉬운 자리만 채운다."""
    props = expression_item()["properties"]

    assert "example" not in props
    assert "example_ko" not in props


def test_each_difficulty_is_defined_by_counting_not_by_adjectives():
    """**`08 §1` 의 교훈이다** — "깊게"·"최소한으로" 는 판정할 수 없다.
    예문 난이도는 단어 수와 절 개수로 적혀서 세어 확인할 수 있다."""
    from app.prompts.analysis import _EXAMPLE_RULE

    assert "[examples]" in _EXAMPLE_RULE, "규칙 덩이를 잘못 집었다"
    for name in ("beginner", "intermediate", "advanced"):
        assert name in _EXAMPLE_RULE, name
    # 세 난이도마다 단어 수 범위가 적혀 있다.
    import re

    ranges = re.findall(r"(\d+)~(\d+) 단어", _EXAMPLE_RULE)
    assert len(ranges) == 3, ranges
    lows = [int(low) for low, _ in ranges]
    assert lows == sorted(lows), "난이도가 올라갈수록 길어져야 한다"


def test_the_example_rule_offers_no_way_out():
    """생략할 길을 적어 두면 작은 모델은 그 길로 간다 (H-021)."""
    from app.prompts.analysis import _EXAMPLE_RULE

    assert "세 개 모두 반드시 넣는다" in _EXAMPLE_RULE
    # "생략" 은 `생략하지 말고` 한 군데에만 나와야 한다.
    assert _EXAMPLE_RULE.count("생략") == _EXAMPLE_RULE.count("생략하지 말고"), (
        "예문 규칙에 생략 조항이 다시 들어왔다"
    )


def test_the_korean_gloss_rule_pins_the_subject():
    """`H-046` — 대역이 주어를 바꿔 옮겼다 (`She acted…` → "그는…")."""
    from app.prompts.analysis import _EXAMPLE_RULE

    assert "주어와 인물을 바꾸지 않는다" in _EXAMPLE_RULE


def test_the_expressions_task_is_a_plain_string_now():
    """난이도마다 조립하던 함수가 사라졌다 — 조립할 것이 없다."""
    assert isinstance(expressions_spec().task, str)


async def test_nuance_is_rendered_below_the_table():
    """뉘앙스는 길어서 표 칸에 넣으면 좁아 깨진다."""
    payload = dict(PART_PAYLOADS["expressions"])
    payload["expressions"] = [
        {**payload["expressions"][0], "nuance": "대서양을 연못에 빗댄 표현이다."}
    ]
    service = AnalyzerService(FakeProvider({"expressions": json.dumps(payload, ensure_ascii=False)}))
    events = await collect(service)
    md = next(e for e in events if isinstance(e, PartEvent) and e.field == "expressions").markdown

    assert "| 표현 (영어) |" in md
    assert "* **across the pond** — 대서양을 연못에 빗댄 표현이다." in md


def test_overview_markdown_skips_empty_rows():
    """옛 기록을 올리면 tone 처럼 없는 칸이 빈 값으로 남는다. 라벨만 덩그러니 두지 않는다."""
    from app.schemas import Overview
    from app.services.markdown import render_overview

    md = render_overview(
        Overview(domain="소설", tone="", formality="격식", style="문어체", comment="코멘트")
    )

    assert "**분야**: 소설" in md
    assert "**톤**" not in md


# ------------------------------------------------- 스키마를 두 겹으로 건다 (M12-T3)
# 왜 두 겹인지는 04-prompt-design.md §10.


NARROW = SchemaLimits(takes_max_items=False, min_items_allowed=(0, 1))

REQUEST = AnalyzeRequest(text="It's unlikely to find its way across the pond.")

# 개수만 어기고 **칸은 다 채운** 응답. 칸이 비면 파이단틱이 먼저 잡아서
# 되재기가 돌았는지 알 수 없게 된다.
def many(count: int) -> str:
    one = PART_PAYLOADS["expressions"]["expressions"][0]
    return json.dumps(
        {"expressions": [one | {"expression": f"e{i}"} for i in range(count)]},
        ensure_ascii=False,
    )


def sent_for(provider: FakeProvider, field: str) -> dict:
    """그 파트에 **실제로 보낸** 스키마."""
    for schema in provider.schemas:
        if schema and field in schema.get("properties", {}):
            return schema
    raise AssertionError(f"{field} 파트를 안 보냈다")


def bounds(schema: dict, field: str) -> dict:
    return schema["properties"][field]


async def test_a_provider_that_takes_everything_is_sent_the_counts():
    """기본 경로. **이게 안 되면 개수 강제가 애초에 없다** (04 §2.1.2)."""
    provider = FakeProvider()
    await AnalyzerService(provider).analyze(REQUEST)

    array = bounds(sent_for(provider, "expressions"), "expressions")
    assert array["maxItems"] == 8
    assert array["minItems"] >= 1


async def test_a_narrow_provider_is_not_sent_what_it_would_reject():
    """Anthropic 은 `maxItems` 를 받으면 400 이다. 보내면 분석 자체가 죽는다."""
    provider = FakeProvider()
    provider.schema_limits = NARROW
    await AnalyzerService(provider).analyze(REQUEST)

    array = bounds(sent_for(provider, "expressions"), "expressions")
    assert "maxItems" not in array
    assert "3개" in array.get("description", "") or array.get("minItems") in (0, 1)


async def test_a_narrow_provider_still_has_its_counts_measured():
    """**깎았다고 풀어 주지 않는다.**

    상한을 못 실어 보낸 제공자가 9개를 돌려주면, 전에는 그대로 통과했다.
    이제 되재기가 잡고 재시도를 부른다.
    """
    provider = FakeProvider(overrides={"expressions": many(9)})
    provider.schema_limits = NARROW

    result = await AnalyzerService(provider).analyze(REQUEST)

    assert "expressions" in result.meta.failed_parts
    # 두 번 시도하고 포기한다.
    assert sum(1 for f, _ in provider.calls if f == "expressions") == 2


async def test_a_count_violation_says_how_many_came_back():
    """재시도해도 안 되면 그 숫자가 오류에 남아야 한다 — "어긋났다" 만으로는 못 고친다.

    건수는 `meta.failed_parts` 에 안 실린다(이름만 들고 있다). 스트림의
    `part_error` 가 자세한 내용을 드는 자리다.
    """
    provider = FakeProvider(overrides={"expressions": many(9)})
    provider.schema_limits = NARROW
    service = AnalyzerService(provider)

    events = [e async for e in service.stream(REQUEST)]
    failed = next(
        e for e in events if isinstance(e, PartErrorEvent) and e.field == "expressions"
    )

    assert "9개" in (failed.detail or "")


async def test_a_wide_provider_has_its_counts_measured_too():
    """되재기는 **제공자를 가리지 않는다.**

    Anthropic 때문에 만들었지만, 스키마를 실어 보냈다는 사실을 지켜졌다는 뜻으로
    읽고 있었던 것이 원래 구멍이다. Gemini 가 어겨도 이제 잡힌다.
    """
    provider = FakeProvider(overrides={"expressions": many(9)})

    result = await AnalyzerService(provider).analyze(REQUEST)

    assert "expressions" in result.meta.failed_parts
