"""Gemini 프로바이더 — **사고 수준**과 모델 목록 (M3-T7).

`-lite` 가 아닌 flash 는 사고 모델이다. 안 걸면 짧은 답 하나에도 토큰을 수백 개
쓰고, **그 비용은 회원의 한도가 치른다.** 실측은 13-gemini-benchmark.md §2.2.
"""

import json

import httpx
import pytest

from app.providers import registry
from app.providers.base import ChatMessage
from app.providers.gemini import GeminiProvider

GEMINI_MODELS = registry.BY_ID[registry.GEMINI].models

MESSAGES = [ChatMessage(role="user", content="hello")]


def make_provider(seen: dict, **kwargs) -> GeminiProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gemini-3.5-flash-lite",
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                "usage": {"completion_tokens": 1},
            },
        )

    client = httpx.AsyncClient(
        base_url="https://example.invalid", transport=httpx.MockTransport(handler)
    )
    return GeminiProvider("AIzaTEST", client=client, **kwargs)


async def test_the_reasoning_level_goes_out_with_the_request():
    """**기본값이 나가는지 본다.** 안 나가면 토큰이 8배 든다 — 조용히 비싸진다."""
    seen: dict = {}
    provider = make_provider(seen)
    await provider.complete(MESSAGES)
    await provider.aclose()

    assert seen["reasoning_effort"] == "low"


async def test_an_empty_level_is_not_sent_at_all():
    """빈 문자열은 **안 보낸다.** 빈 값을 보내면 400 이 난다."""
    seen: dict = {}
    provider = make_provider(seen, reasoning_effort="")
    await provider.complete(MESSAGES)
    await provider.aclose()

    assert "reasoning_effort" not in seen


async def test_the_level_can_be_changed():
    seen: dict = {}
    provider = make_provider(seen, reasoning_effort="high")
    await provider.complete(MESSAGES)
    await provider.aclose()

    assert seen["reasoning_effort"] == "high"


def test_the_settings_value_reaches_the_provider(monkeypatch):
    """설정 → `registry.build` → 요청. **중간에 끊기면 아무것도 안 말해 준다.**"""
    from app.config import get_settings

    monkeypatch.setenv("GEMINI_REASONING_EFFORT", "high")
    get_settings.cache_clear()
    provider = registry.build(
        registry.GEMINI, "gemini-3.5-flash-lite", "AIzaTEST", get_settings()
    )

    assert provider._reasoning_effort == "high"


# ------------------------------------------------------------------- 모델 목록


def test_the_cheapest_model_is_the_default():
    """**첫 번째가 기본값이다.** 사고 모델이 첫 줄에 오면 모든 회원이 더 낸다."""
    assert registry.BY_ID[registry.GEMINI].models[0] == "gemini-3.5-flash-lite"


@pytest.mark.parametrize("model", GEMINI_MODELS)
def test_every_offered_model_is_a_flash_model(model):
    """고를 수 있는 것은 flash 계열뿐이다 — 다른 계열은 비용이 다른 자리에 있다."""
    assert "flash" in model
    # `-latest` 별칭은 **움직이는 과녁**이다. 지금 무엇으로 돌았는지 추적할 수 없다.
    assert not model.endswith("-latest")
    # `-preview` 는 이름이 사라질 수 있다.
    assert "preview" not in model
