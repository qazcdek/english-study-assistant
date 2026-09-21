"""llama.cpp `llama-server` 프로바이더 (로컬 모드).

llama-server 는 OpenAI 호환 `/v1/chat/completions` 를 제공하므로 공통 구현을 쓰고,
llama.cpp 고유의 두 가지만 덧붙인다.

1. `response_format` 형태가 서버 버전마다 달라 `json_mode` 로 고른다.
2. Qwen3 같은 reasoning 모델의 사고를 `chat_template_kwargs` 로 끈다.
   켜 두면 사고가 `max_tokens` 를 전부 소진해 본문이 빈 채로 돌아온다
   (documents/05-benchmark.md).
"""

from typing import Any

import httpx

from app.providers.openai_compatible import OpenAICompatibleProvider


class LlamaServerProvider(OpenAICompatibleProvider):
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
        super().__init__(
            base_url,
            model=model,
            api_key=api_key,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            client=client,
        )
        self.json_mode = json_mode
        self.enable_thinking = enable_thinking

    def _response_format(self, json_schema: dict[str, Any] | None) -> dict[str, Any] | None:
        if json_schema is None or self.json_mode == "none":
            return None
        if self.json_mode == "json_object":
            # 구버전 llama-server: json_object 안에 schema 를 직접 넣는다.
            return {"type": "json_object", "schema": json_schema}
        return super()._response_format(json_schema)

    def _extra_payload(self) -> dict[str, Any]:
        if self.enable_thinking is None:
            return {}
        # 채팅 템플릿이 이 인자를 모르면 llama-server 가 조용히 무시한다.
        return {"chat_template_kwargs": {"enable_thinking": self.enable_thinking}}
