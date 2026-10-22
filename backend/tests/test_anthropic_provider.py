"""Anthropic 프로바이더 (M12-T3).

**OpenAI 호환이 아니다** — 갈리는 넷을 전부 고정한다.
왜 개수 제약을 못 싣는지는 04-prompt-design.md §10.
"""

import json

import httpx

from app.errors import LLMError, LLMTruncatedError, LLMUnavailableError
from app.providers.anthropic import (
    API_VERSION,
    BASE_URL,
    AnthropicProvider,
    join_text,
    split_system,
)
from app.providers.base import ChatMessage

MESSAGES = [
    ChatMessage(role="system", content="너는 분석기다"),
    ChatMessage(role="user", content="hello"),
]
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}}


def make_provider(handler, **kwargs) -> AnthropicProvider:
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return AnthropicProvider("sk-ant-test", client=client, **kwargs)


def ok(text: str = '{"a": "b"}', *, stop_reason: str = "end_turn") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "claude-sonnet-5-5",
            "stop_reason": stop_reason,
            "content": [{"type": "text", "text": text}],
            "usage": {"output_tokens": 12},
        },
    )


def capture(seen: dict, response=None):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["__headers__"] = dict(request.headers)
        seen["__path__"] = request.url.path
        return response or ok()

    return handler


# -------------------------------------------------------- 갈리는 넷을 고정한다


async def test_it_posts_to_the_messages_endpoint():
    seen: dict = {}
    await make_provider(capture(seen)).complete(MESSAGES)

    assert seen["__path__"] == "/v1/messages"


async def test_the_key_goes_in_x_api_key_with_a_pinned_version():
    """`Authorization: Bearer` 가 아니다. 버전 헤더가 없으면 거부당한다.

    **클라이언트를 주지 않고** 만든다 — 목 클라이언트에 헤더를 직접 달고 그걸
    확인하면 내 픽스처를 확인하는 것이지 구현을 확인하는 것이 아니다.
    """
    provider = AnthropicProvider("sk-ant-test")
    try:
        assert provider._client.headers["x-api-key"] == "sk-ant-test"
        assert provider._client.headers["anthropic-version"] == API_VERSION
        assert "authorization" not in provider._client.headers
    finally:
        await provider.aclose()


async def test_system_leaves_the_messages_array():
    seen: dict = {}
    await make_provider(capture(seen)).complete(MESSAGES)

    assert seen["system"] == "너는 분석기다"
    assert [m["role"] for m in seen["messages"]] == ["user"]


async def test_the_schema_goes_in_output_config_not_response_format():
    seen: dict = {}
    await make_provider(capture(seen)).complete(MESSAGES, json_schema=SCHEMA)

    assert seen["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert "response_format" not in seen


async def test_max_tokens_is_always_sent():
    """**여기서는 필수다.** 빼면 400 이 난다 — OpenAI 쪽처럼 기본값이 쓰이지 않는다."""
    seen: dict = {}
    await make_provider(capture(seen)).complete(MESSAGES)

    assert seen["max_tokens"] > 0


# ------------------------------------------------------------ 개수 제약의 범위


def test_it_declares_that_it_cannot_carry_the_counts():
    limits = AnthropicProvider.schema_limits

    assert not limits.takes_max_items
    assert limits.keeps_min_items(1)
    assert limits.keeps_min_items(0)
    assert not limits.keeps_min_items(2)


# ------------------------------------------- 거절·잘림을 본문보다 먼저 본다


async def test_a_refusal_arrives_as_200_and_is_not_read_as_an_answer():
    """거절은 HTTP 200 으로 온다. `content` 를 먼저 읽으면 정상 응답으로 착각한다."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "claude-sonnet-5-5",
                "stop_reason": "refusal",
                "content": [],
                "usage": {"output_tokens": 0},
            },
        )

    try:
        await make_provider(handler).complete(MESSAGES)
    except LLMError as exc:
        assert "거부" in str(exc)
    else:
        raise AssertionError("거절을 정상 응답으로 통과시켰다")


async def test_hitting_the_token_cap_is_a_truncation_not_a_bad_answer():
    """잘린 것은 재시도해도 같으므로 다른 오류로 올려보내야 한다."""
    try:
        await make_provider(lambda r: ok(stop_reason="max_tokens")).complete(MESSAGES)
    except LLMTruncatedError as exc:
        assert "12" in str(exc)
    else:
        raise AssertionError("잘린 응답을 그냥 통과시켰다")


async def test_an_empty_body_is_an_error_not_an_empty_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "claude-sonnet-5-5", "stop_reason": "end_turn", "content": []},
        )

    try:
        await make_provider(handler).complete(MESSAGES)
    except LLMError:
        pass
    else:
        raise AssertionError("빈 본문을 통과시켰다")


# ------------------------------------------------------------------ 오류 안내


async def test_a_rejected_key_says_what_to_check():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    try:
        await make_provider(handler).complete(MESSAGES)
    except LLMUnavailableError as exc:
        assert "Anthropic" in str(exc)
    else:
        raise AssertionError("401 을 그냥 통과시켰다")


# -------------------------------------------------------------- 순수 함수 둘
# 전송을 세우지 않고 모양만 본다.


def test_several_system_messages_are_joined_not_dropped():
    """길들이기 문구가 system 에 들어 있다 (04 §9). 버리면 조용히 품질이 바뀐다."""
    system, turns = split_system(
        [
            ChatMessage(role="system", content="하나"),
            ChatMessage(role="system", content="둘"),
            ChatMessage(role="user", content="본문"),
        ]
    )

    assert system == "하나\n\n둘"
    assert len(turns) == 1


def test_no_system_message_means_no_system_field():
    system, turns = split_system([ChatMessage(role="user", content="본문")])

    assert system == ""
    assert len(turns) == 1


def test_text_is_gathered_from_every_text_block():
    """사고 블록이 앞에 올 수 있다. 첫 블록만 집으면 빈 문자열을 집는다."""
    data = {
        "content": [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": '{"a":'},
            {"type": "text", "text": ' "b"}'},
        ]
    }

    assert join_text(data) == '{"a": "b"}'


def test_a_missing_content_list_is_an_empty_string():
    assert join_text({}) == ""
