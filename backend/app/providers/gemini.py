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


async def verify_api_key(
    api_key: str,
    *,
    base_url: str,
    model: str,
    timeout: float = 20.0,
) -> tuple[bool, str | None]:
    """키를 저장하기 전에 실제로 쓸 수 있는지 확인한다.

    사용 한도를 거의 쓰지 않도록 아주 짧은 요청 하나만 보낸다.
    """
    provider = GeminiProvider(api_key, base_url=base_url, model=model, timeout=timeout)
    try:
        from app.providers.base import ChatMessage

        await provider.complete(
            [ChatMessage(role="user", content="Reply with the single word: ok")],
            temperature=0.0,
            max_tokens=8,
        )
        return True, None
    except Exception as exc:  # noqa: BLE001 - 사용자에게 보여줄 메시지로 바꾼다
        return False, str(exc)
    finally:
        await provider.aclose()
