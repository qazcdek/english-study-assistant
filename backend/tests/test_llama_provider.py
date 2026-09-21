import json

import httpx
import pytest

from app.errors import LLMTruncatedError, LLMUnavailableError
from app.providers.base import ChatMessage
from app.providers.llama_server import LlamaServerProvider

MESSAGES = [ChatMessage(role="user", content="hello")]
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}}


def make_provider(handler, **kwargs) -> LlamaServerProvider:
    client = httpx.AsyncClient(
        base_url="http://llm.test/v1", transport=httpx.MockTransport(handler)
    )
    return LlamaServerProvider("http://llm.test/v1", client=client, **kwargs)


def ok_response(request: httpx.Request, *, finish_reason="stop", content="{}", reasoning=""):
    return httpx.Response(
        200,
        json={
            "model": "qwen3.8-27b",
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"content": content, "reasoning_content": reasoning},
                }
            ],
            "usage": {"completion_tokens": 2048},
        },
    )


async def test_sends_json_schema_and_disables_thinking_by_default():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return ok_response(request, content='{"a": "b"}')

    provider = make_provider(handler)
    result = await provider.complete(MESSAGES, json_schema=SCHEMA)

    assert result.text == '{"a": "b"}'
    assert seen["response_format"]["type"] == "json_schema"
    assert seen["response_format"]["json_schema"]["schema"] == SCHEMA
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}


async def test_json_object_mode_uses_legacy_shape():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return ok_response(request)

    provider = make_provider(handler, json_mode="json_object")
    await provider.complete(MESSAGES, json_schema=SCHEMA)

    assert seen["response_format"] == {"type": "json_object", "schema": SCHEMA}


async def test_thinking_kwargs_omitted_when_unset():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return ok_response(request)

    provider = make_provider(handler, enable_thinking=None)
    await provider.complete(MESSAGES, json_schema=SCHEMA)

    assert "chat_template_kwargs" not in seen


async def test_truncated_response_raises_clear_error():
    """reasoning 모델이 사고에 max_tokens 를 다 써서 content 가 비는 경우."""

    def handler(request: httpx.Request) -> httpx.Response:
        return ok_response(request, finish_reason="length", content="", reasoning="x" * 7874)

    provider = make_provider(handler)

    with pytest.raises(LLMTruncatedError) as exc:
        await provider.complete(MESSAGES, json_schema=SCHEMA)

    assert "2048" in exc.value.detail
    assert "7874" in exc.value.detail


async def test_connect_error_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = make_provider(handler)

    with pytest.raises(LLMUnavailableError):
        await provider.complete(MESSAGES)
