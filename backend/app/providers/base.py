"""LLM 프로바이더 인터페이스.

서비스 계층은 이 추상 클래스만 알고, 구체 구현(llama-server 등)은 모른다.
다른 백엔드로 갈아끼우려면 이 인터페이스만 구현하면 된다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.providers.schema import SchemaLimits


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class CompletionResult:
    text: str
    model: str
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """채팅 방식 LLM에 대한 최소 인터페이스."""

    # 프롬프트를 고르는 데 쓴다 (`prompts/models.py`). **기본값을 둔다** —
    # 구현이 안 채워도 돌아야 하고, 빈 값이면 모델별 덧붙임 없이 base 를 쓴다.
    # 전에는 선언만 있어서 인스턴스에 없었고, 모델별 프롬프트를 붙이는 순간
    # 테스트 가짜 전부가 깨졌다 (M3-T5).
    model: str = ""

    # 와이어 스키마가 실을 수 있는 범위. **기본값은 "전부 받는다"** 이고,
    # 좁은 쪽만 덮어쓴다. 왜 이것이 필요한지는 `providers/schema.py`.
    schema_limits: SchemaLimits = SchemaLimits()

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """메시지를 보내고 텍스트 응답을 받는다.

        `json_schema` 가 주어지면 응답이 해당 스키마를 따르도록 모델에 강제한다.
        강제 수단이 없는 구현이라면 최소한 JSON 객체만 나오도록 유도해야 한다.

        **부르는 쪽이 `schema_limits` 로 미리 깎아서 넘긴다** — 구현이 다시
        깎지 않는다. 깎은 자리를 모르면 돌아온 응답을 다시 잴 수 없다.
        """

    @abstractmethod
    async def health(self) -> tuple[bool, list[str], str | None]:
        """(연결 가능 여부, 모델 목록, 상세 메시지) 를 돌려준다."""

    async def aclose(self) -> None:
        """리소스 정리. 필요 없는 구현은 그대로 둔다."""
        return
