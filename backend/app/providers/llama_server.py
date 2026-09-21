"""llama.cpp `llama-server` 프로바이더.

llama-server 는 OpenAI 호환 `/v1/chat/completions` 를 제공하므로 그대로 사용한다.
서버 자체는 이 저장소가 관리하지 않는다 — 사용자가 직접 띄우고 `LLM_BASE_URL` 로 가리킨다.

    llama-server -m model.gguf -c 8192 --host 127.0.0.1 --port 8080 --jinja

JSON 스키마 강제는 세 가지 모드를 지원한다 (`LLM_JSON_MODE`):
  - json_schema : OpenAI 형식 `response_format.json_schema`. 최신 llama-server 권장.
  - json_object : `{"type": "json_object", "schema": ...}` — 구버전 llama-server 방식.
  - none        : 서버가 스키마를 못 받을 때. 프롬프트로만 유도하고 파싱은 서비스가 방어한다.

Qwen3 같은 reasoning 모델은 `--jinja` 로 띄우면 사고 과정을 `reasoning_content` 로 따로 내보내는데,
이때도 토큰은 `max_tokens` 를 함께 갉아먹는다. 사고가 길어지면 한도가 사고에서 다 소진되어
`content` 가 빈 문자열로 돌아온다. `enable_thinking=False` 로 사고를 끄는 것이 기본값이다.
"""

from typing import Any

import httpx

from app.errors import LLMError, LLMTimeoutError, LLMTruncatedError, LLMUnavailableError
from app.providers.base import ChatMessage, CompletionResult, LLMProvider


class LlamaServerProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        *,
        model: str = "local-model",
        api_key: str = "",
        timeout: float = 300.0,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        json_mode: str = "json_schema",
        enable_thinking: bool | None = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.json_mode = json_mode
        self.enable_thinking = enable_thinking

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
        if self.enable_thinking is not None:
            # Qwen3 등 하이브리드 reasoning 모델의 채팅 템플릿에 전달된다.
            # 템플릿이 이 인자를 모르면 llama-server 가 조용히 무시한다.
            payload["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}

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
            resp = await self._client.get("/models", timeout=5.0)
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

    def _response_format(self, json_schema: dict[str, Any] | None) -> dict[str, Any] | None:
        if json_schema is None or self.json_mode == "none":
            return None
        if self.json_mode == "json_object":
            # 구버전 llama-server: json_object 안에 schema 를 직접 넣는다.
            return {"type": "json_object", "schema": json_schema}
        return {
            "type": "json_schema",
            "json_schema": {"name": "analysis", "strict": True, "schema": json_schema},
        }

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
            raise LLMError(f"llama-server 가 {resp.status_code} 를 반환했습니다: {resp.text[:500]}")

        return resp.json()
