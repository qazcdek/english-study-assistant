"""OpenAI 프로바이더 (M12-T3).

갈리는 것은 추론 모델의 파라미터 둘이다 — 04-prompt-design.md §10.4.
"""

import json

import httpx

from app.errors import LLMUnavailableError
from app.providers.base import ChatMessage
from app.providers.openai import BASE_URL, OpenAIProvider

MESSAGES = [ChatMessage(role="user", content="hello")]
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}}


def make_provider(handler, **kwargs) -> OpenAIProvider:
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return OpenAIProvider("sk-test", client=client, **kwargs)


def ok(content: str = "{}", *, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "gpt-5-mini",
            "choices": [{"finish_reason": finish_reason, "message": {"content": content}}],
            "usage": {"completion_tokens": 10},
        },
    )


def capture(seen: dict, response=None):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["__headers__"] = dict(request.headers)
        seen["__path__"] = request.url.path
        return response or ok('{"a": "b"}')

    return handler


# ------------------------------------------------------------------ 공통 규격


async def test_it_talks_the_openai_compatible_shape():
    """**OpenAI 가 이 규격의 원본이므로** 공통 구현이 그대로 맞아야 한다."""
    seen: dict = {}
    result = await make_provider(capture(seen)).complete(MESSAGES, json_schema=SCHEMA)

    assert result.text == '{"a": "b"}'
    assert seen["__path__"] == "/v1/chat/completions"
    assert seen["response_format"]["json_schema"]["strict"] is True
    assert seen["response_format"]["json_schema"]["schema"] == SCHEMA


async def test_the_key_goes_in_the_bearer_header():
    """**클라이언트를 주지 않고** 만든다 — 헤더를 세우는 쪽이 검사 대상이다.

    목 클라이언트에 헤더를 직접 달아 두고 그것을 확인하면 내 픽스처를 확인하는
    것이지 구현을 확인하는 것이 아니다.
    """
    provider = OpenAIProvider("sk-test")
    try:
        assert provider._client.headers["authorization"] == "Bearer sk-test"
        assert provider.base_url == BASE_URL
    finally:
        await provider.aclose()


async def test_it_takes_every_schema_constraint():
    """OpenAI strict 모드는 `minItems`/`maxItems` 를 받는다.

    **전에는 받지 않는다고 적어 뒀다.** 문서를 읽지 않고 적은 것이었고,
    그 한 줄이 이 제공자를 한 마일스톤 동안 막고 있었다.
    """
    provider = make_provider(capture({}))

    assert provider.schema_limits.takes_max_items
    assert provider.schema_limits.keeps_min_items(8)


# -------------------------------------------------------------- 추론 모델 분기


async def test_a_reasoning_model_gets_max_completion_tokens():
    seen: dict = {}
    await make_provider(capture(seen), model="gpt-5").complete(MESSAGES, max_tokens=512)

    assert seen["max_completion_tokens"] == 512
    assert "max_tokens" not in seen


async def test_a_reasoning_model_is_sent_no_temperature():
    """기본값(1) 말고는 거부한다. 재시도의 `temperature=0` 도 보내지 않는다."""
    seen: dict = {}
    await make_provider(capture(seen), model="gpt-5").complete(MESSAGES, temperature=0.0)

    assert "temperature" not in seen


async def test_a_plain_model_keeps_both_parameters():
    """추론 모델이 아니면 손대지 않는다. **전부에 적용하면 멀쩡한 손잡이를 잃는다.**"""
    seen: dict = {}
    await make_provider(capture(seen), model="gpt-4o").complete(
        MESSAGES, max_tokens=512, temperature=0.0
    )

    assert seen["max_tokens"] == 512
    assert seen["temperature"] == 0.0


async def test_the_family_is_read_from_the_name_not_the_version():
    """`o3-mini` 도 `gpt-5-nano` 도 추론 모델이다. 버전으로 가르지 않는다."""
    for model in ("gpt-5", "gpt-5-mini", "gpt-5-nano", "o1", "o3-mini", "o4-mini"):
        assert make_provider(capture({}), model=model).reasoning, model
    for model in ("gpt-4o", "gpt-4.1-mini"):
        assert not make_provider(capture({}), model=model).reasoning, model


# ------------------------------------------------------------------ 오류 안내


async def test_a_rejected_key_says_what_to_check():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    try:
        await make_provider(handler).complete(MESSAGES)
    except LLMUnavailableError as exc:
        assert "OpenAI" in str(exc)
        assert "키" in str(exc)
    else:
        raise AssertionError("401 을 그냥 통과시켰다")


async def test_a_quota_error_says_it_is_the_members_own_limit():
    """키가 회원 본인의 것이므로 **한도도 회원의 것**이다. 서버 탓으로 읽히면 안 된다."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    try:
        await make_provider(handler).complete(MESSAGES)
    except LLMUnavailableError as exc:
        assert "한도" in str(exc)
    else:
        raise AssertionError("429 를 그냥 통과시켰다")
