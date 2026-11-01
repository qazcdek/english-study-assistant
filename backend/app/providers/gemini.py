"""Gemini 프로바이더 (웹 배포 모드).

Google 은 OpenAI 호환 엔드포인트를 제공하므로 공통 구현을 그대로 쓴다.
    https://generativelanguage.googleapis.com/v1beta/openai/chat/completions

**API 키는 회원 본인의 것이다.** 서버는 키를 보관만 하고(암호화), 호출은 회원 명의로
회원의 사용 한도 안에서 이루어진다. 그래서 프로바이더가 요청마다 새로 만들어진다.
"""


import httpx

from app.providers.openai_compatible import OpenAICompatibleProvider


class GeminiProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
        model: str = "gemini-3.5-flash-lite",
        timeout: float = 120.0,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        reasoning_effort: str = "low",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # **사고를 낮춰 보낸다.** `-lite` 가 아닌 flash 는 사고 모델이고, 안 걸면
        # 짧은 답 하나에 수백 토큰을 쓴다 — 그 비용은 회원의 한도가 치른다.
        # `low` 는 lite 와 사고 모델 **양쪽에서** 받는다 (`none` 은 lite 가 400).
        self._reasoning_effort = reasoning_effort
        super().__init__(
            base_url,
            model=model,
            api_key=api_key,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            client=client,
        )

    def _extra_payload(self) -> dict:
        """사고 수준을 얹는다. 비워 두면 보내지 않는다 (`M3-T7`)."""
        if not self._reasoning_effort:
            return {}
        return {"reasoning_effort": self._reasoning_effort}

    def _describe_auth_error(self, status: int, body: str) -> str | None:
        if status in (401, 403):
            return (
                "등록하신 Gemini API 키가 거부되었습니다. "
                "키가 유효한지, Generative Language API 가 켜져 있는지 확인해 주세요."
            )
        if status == 429:
            return (
                "Gemini 사용 한도를 넘었습니다. 회원님 계정의 한도가 회복되면 다시 시도해 주세요."
            )
        return None
