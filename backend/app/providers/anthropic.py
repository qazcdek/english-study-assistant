"""Anthropic 프로바이더.

**OpenAI 호환이 아니다.** 공통 구현(`openai_compatible.py`)을 못 쓰고 전송 계층을
따로 든다. 갈리는 지점이 넷이다.

```
경로      /v1/messages                  (/chat/completions 이 아니다)
인증      x-api-key + anthropic-version (Authorization: Bearer 가 아니다)
system    messages 밖의 별도 필드        (role="system" 메시지가 아니다)
스키마    output_config.format           (response_format 이 아니다)
```

### 개수 제약을 못 싣는다

`minItems` 는 **0 또는 1만** 받고 `maxItems` 는 아예 안 받는다 — 어기면 400 이다.
이 앱은 표현 개수를 바로 그것으로 강제하므로(04 §2.1.2) 그대로는 못 보낸다.
깎아 보내고 돌아온 응답을 다시 재는 쪽으로 풀었다 — `providers/schema.py`.

**문서를 읽은 것이고 호출해 확인하지 않았다** (M12-T3).
근거: https://platform.claude.com/docs/en/build-with-claude/structured-outputs

### 거절은 오류가 아니라 200 으로 온다

안전 분류기가 요청을 거절하면 HTTP 200 에 `stop_reason: "refusal"` 이 실린다.
`content` 를 먼저 읽으면 빈 텍스트를 정상 응답으로 착각한다. 그래서
`stop_reason` 을 **먼저** 본다.

[문서] plan/DONE.md M12-T3
"""

from typing import Any

import httpx

from app.errors import (
    LLMError,
    LLMTimeoutError,
    LLMTruncatedError,
    LLMUnavailableError,
)
from app.providers.base import ChatMessage, CompletionResult, LLMProvider
from app.providers.schema import SchemaLimits

BASE_URL = "https://api.anthropic.com/v1"

# 날짜 붙은 고정 버전을 보낸다. 안 보내면 거부당하고, 최신을 자동으로 따라가면
# 어느 날 응답 모양이 바뀌어도 모른다.
API_VERSION = "2023-06-01"

# `minItems` 는 0·1 만, `maxItems` 는 못 싣는다.
LIMITS = SchemaLimits(takes_max_items=False, min_items_allowed=(0, 1))


class AnthropicProvider(LLMProvider):
    schema_limits = LIMITS

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        model: str = "claude-sonnet-5-5",
        timeout: float = 120.0,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": API_VERSION,
            },
        )

    # ------------------------------------------------------------------ public

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> CompletionResult:
        system, turns = split_system(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            # **필수다.** OpenAI 쪽은 빼면 기본값이 쓰이지만 여기는 400 이 난다.
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "messages": [m.to_dict() for m in turns],
        }
        if system:
            payload["system"] = system
        if json_schema is not None:
            payload["output_config"] = {
                "format": {"type": "json_schema", "schema": json_schema}
            }

        data = await self._post("/messages", payload)

        # 거절·잘림을 **본문보다 먼저** 본다.
        stop = data.get("stop_reason")
        if stop == "refusal":
            raise LLMError(
                "모델이 이 요청에 답하기를 거부했습니다. 다른 문단으로 시도해 주세요."
            )
        if stop == "max_tokens":
            used = data.get("usage", {}).get("output_tokens", "?")
            raise LLMTruncatedError(f"output_tokens={used} 에서 잘렸습니다.")

        text = join_text(data)
        if not text:
            raise LLMError(f"본문이 비어 있습니다: {data!r}")

        return CompletionResult(text=text, model=data.get("model", self.model), raw=data)

    async def health(self) -> tuple[bool, list[str], str | None]:
        try:
            resp = await self._client.get("/models", timeout=8.0)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            return False, [], str(exc)

        models = [m.get("id", "") for m in body.get("data", []) if isinstance(m, dict)]
        return True, [m for m in models if m], None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ----------------------------------------------------------------- private

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(f"{self.base_url} 에 연결할 수 없습니다: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(str(exc)) from exc

        if resp.status_code >= 400:
            described = _describe(resp.status_code)
            if described:
                raise LLMUnavailableError(described)
            raise LLMError(f"{resp.status_code} 응답: {resp.text[:500]}")

        return resp.json()


# ------------------------------------------------------------------ 순수 함수
# 전송과 떼어 둔다. HTTP 를 세우지 않고 모양만 검사할 수 있어야 한다.


def split_system(messages: list[ChatMessage]) -> tuple[str, list[ChatMessage]]:
    """`system` 을 messages 밖으로 꺼낸다.

    앱의 프롬프트는 system 하나 + user 하나로 짜여 있다. 둘 이상이면 줄바꿈 둘로
    이어 붙인다 — **버리지 않는다.** 길들이기 문구가 거기 들어 있다 (04 §9).
    """
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    return system, [m for m in messages if m.role != "system"]


def join_text(data: dict[str, Any]) -> str:
    """`content` 블록 중 텍스트만 이어 붙인다.

    블록이 여럿일 수 있고 사고(thinking) 블록이 섞일 수 있다. 첫 블록만 집으면
    사고 블록이 앞에 올 때 빈 문자열을 집는다.
    """
    blocks = data.get("content")
    if not isinstance(blocks, list):
        return ""
    return "".join(
        b.get("text", "")
        for b in blocks
        if isinstance(b, dict) and b.get("type") == "text"
    )


def _describe(status: int) -> str | None:
    if status in (401, 403):
        return (
            "등록하신 Anthropic API 키가 거부되었습니다. "
            "키가 유효한지, 크레딧이 남아 있는지 확인해 주세요."
        )
    if status == 429:
        return (
            "Anthropic 사용 한도를 넘었습니다. "
            "회원님 계정의 한도가 회복되면 다시 시도해 주세요."
        )
    return None
