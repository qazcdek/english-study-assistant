"""OpenAI 프로바이더.

OpenAI 가 `/chat/completions` 규격의 원본이므로 공통 구현을 거의 그대로 쓴다.
**다만 추론 모델(`gpt-5` 계열)에서 두 파라미터가 갈린다.**

```
max_tokens      deprecated. 추론 모델은 거부한다 → max_completion_tokens
temperature     기본값(1) 말고는 거부한다       → 아예 안 보낸다
```

둘 다 **문서를 읽은 것이고 호출해 확인하지 않았다** (M12-T3).
근거: https://developers.openai.com/api/docs/api-reference/chat/create

### 재시도에서 잃는 것

공통 구현은 형식이 어긋나면 `temperature=0` 으로 한 번 더 시도한다. 여기서는
그 손잡이가 없으므로 **재시도가 길들이기 문구(04 §9)에만 의지한다.**
온도를 낮추는 쪽이 더 센 수단이었으니, 이 프로바이더의 재시도는 그만큼 약하다.

[문서] 04-prompt-design.md §10.4
[문서] plan/DONE.md M12-T3
"""

import httpx

from app.providers.openai_compatible import OpenAICompatibleProvider

BASE_URL = "https://api.openai.com/v1"

# 이 글자가 모델 이름에 있으면 추론 모델로 본다. 버전이 아니라 계열로 가른다 —
# `prompts/models.py` 의 `_MARKS` 와 같은 이유다.
_REASONING = ("gpt-5", "o1", "o3", "o4")


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        model: str = "gpt-5-mini",
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

    @property
    def reasoning(self) -> bool:
        return any(mark in self.model.lower() for mark in _REASONING)

    def _finalize_payload(self, payload: dict) -> dict:
        """추론 모델이 거부하는 두 파라미터를 바꿔 끼운다."""
        if not self.reasoning:
            return payload
        payload["max_completion_tokens"] = payload.pop("max_tokens")
        payload.pop("temperature", None)
        return payload

    def _describe_auth_error(self, status: int, body: str) -> str | None:
        if status in (401, 403):
            return (
                "등록하신 OpenAI API 키가 거부되었습니다. "
                "키가 유효한지, 결제 수단이 등록되어 있는지 확인해 주세요."
            )
        if status == 429:
            return (
                "OpenAI 사용 한도를 넘었습니다. "
                "회원님 계정의 한도가 회복되면 다시 시도해 주세요."
            )
        return None
