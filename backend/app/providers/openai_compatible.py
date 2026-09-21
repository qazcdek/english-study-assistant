"""OpenAI 호환 `/chat/completions` 를 쓰는 프로바이더의 공통 구현.

llama-server 와 Gemini 둘 다 이 규격을 제공하므로 전송 계층을 공유한다.
차이나는 부분(인증 헤더, 추가 파라미터, 상태 확인)만 하위 클래스가 채운다.
"""

from typing import Any

import httpx

from app.errors import LLMError, LLMTimeoutError, LLMTruncatedError, LLMUnavailableError
from app.providers.base import ChatMessage, CompletionResult, LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        *,
        model: str,
        api_key: str = "",
        timeout: float = 120.0,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers=headers,
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
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        response_format = self._response_format(json_schema)
        if response_format is not None:
            payload["response_format"] = response_format
        payload.update(self._extra_payload())

        data = await self._post("/chat/completions", payload)

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"예상치 못한 응답 형태입니다: {data!r}") from exc

        if choice.get("finish_reason") == "length":
            used = data.get("usage", {}).get("completion_tokens", "?")
            reasoning = len(choice["message"].get("reasoning_content") or "")
            raise LLMTruncatedError(
                f"completion_tokens={used} 에서 잘렸습니다 "
                f"(사고 과정 {reasoning}자, 본문 {len(text)}자)."
            )

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

    # ------------------------------------------------------------------ 확장점

    def _response_format(self, json_schema: dict[str, Any] | None) -> dict[str, Any] | None:
        if json_schema is None:
            return None
        return {
            "type": "json_schema",
            "json_schema": {"name": "analysis", "strict": True, "schema": json_schema},
        }

    def _extra_payload(self) -> dict[str, Any]:
        return {}

    def _describe_auth_error(self, status: int, body: str) -> str | None:
        """401/403 을 사용자에게 보여줄 말로 바꾼다. 필요 없으면 None."""
        return None

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
            described = self._describe_auth_error(resp.status_code, resp.text)
            if described:
                raise LLMUnavailableError(described)
            raise LLMError(f"{resp.status_code} 응답: {resp.text[:500]}")

        return resp.json()
