"""고를 수 있는 LLM 제공자 목록. 규약은 09-mode-matrix.md §3.2.

**전에는 모드가 제공자를 정했다** — local 은 llama-server, cloud 는 Gemini.
이제 회원이 고른다. 다만 고를 수 있는 **범위**는 모드로 갈린다.

```
local    llama-server + cloud LLM 전부
cloud    cloud LLM 만 — llama-server 는 내 PC 에 있어서 Render 에서 닿지 않는다
```

### 왜 목록을 한 곳에 두나

제공자가 늘면 **다섯 곳이 함께 늘어난다** — 프로바이더 구현 · 키 저장 · 프롬프트 계열
(04 §9) · 화면의 선택 UI · **개인정보처리방침의 국외 이전 수탁자**. 목록이 흩어져 있으면
그중 하나를 빼먹고, 빼먹은 것이 방침이면 **적지 않은 곳으로 데이터가 나간다.**

그래서 여기가 유일한 목록이고, 검사가 이 표와 실제 구현을 대조한다.

[문서] 07-web-deployment.md §10.6
"""

from dataclasses import dataclass

from app.providers.anthropic import AnthropicProvider
from app.providers.base import LLMProvider
from app.providers.gemini import GeminiProvider
from app.providers.llama_server import LlamaServerProvider
from app.providers.openai import OpenAIProvider

GEMINI = "gemini"
OPENAI = "openai"
ANTHROPIC = "anthropic"
LLAMA = "llama"


@dataclass(frozen=True)
class ProviderInfo:
    """한 제공자에 대해 알아야 할 전부."""

    id: str
    label: str
    """화면에 보일 이름."""
    models: tuple[str, ...]
    """고를 수 있는 모델. **첫 번째가 기본값이다.**

    아무 문자열이나 받지 않는다 — 오타가 들어오면 호출할 때까지 모르고, 그때는
    회원이 제 키로 실패를 겪는다. 새 모델을 쓰려면 여기 한 줄을 더한다.
    """
    needs_key: bool
    """회원이 키를 등록해야 하나. llama-server 는 내 PC 라 필요 없다."""
    local_only: bool
    """서버가 내 PC 에 있나. 그러면 cloud 에서 고를 수 없다."""
    key_url: str = ""
    note: str = ""
    # 개인정보처리방침의 **국외 이전 표에 적혀야 하는 이름.** 글자 그대로 거기에
    # 있어야 하고, 검사가 그걸 본다 (`test_provider_registry.py`).
    #
    # `label` 로 맞추지 않는다 — 화면에 보일 이름("OpenAI ChatGPT")과 방침에 적을
    # 이름("OpenAI (ChatGPT API)")은 쓰임이 달라서 따로 움직인다. 하나로 묶으면
    # 화면 문구를 다듬다가 방침이 조용히 어긋난다.
    #
    # 내 PC 의 llama-server 는 밖으로 나가지 않으므로 비어 있다.
    transfer_name: str = ""
    """아직 안 되는 것은 **왜 안 되는지** 적는다. 비워 두면 다음 사람이 다시 조사한다."""

    @property
    def implemented(self) -> bool:
        """지금 실제로 돌아가나.

        **선언하지 않고 끌어온다.** 전에는 `implemented: bool` 를 손으로 적었는데,
        거짓으로 적어도 아무것도 안 잡혔다 — 일부러 True 로 바꿔 봤더니 검사가 전부
        통과했다. 구현 표에 있다는 사실이 유일한 근거여야 한다.
        """
        return self.id in IMPLEMENTATIONS


PROVIDERS: tuple[ProviderInfo, ...] = (
    ProviderInfo(
        id=LLAMA,
        label="llama-server (내 PC)",
        models=("local-model",),
        needs_key=False,
        local_only=True,
    ),
    ProviderInfo(
        id=GEMINI,
        label="Google Gemini",
        models=("gemini-3.5-flash-lite",),
        needs_key=True,
        local_only=False,
        key_url="https://aistudio.google.com/apikey",
        transfer_name="Google (Gemini API)",
    ),
    ProviderInfo(
        id=OPENAI,
        label="OpenAI ChatGPT",
        models=("gpt-5", "gpt-5-mini"),
        needs_key=True,
        local_only=False,
        key_url="https://platform.openai.com/api-keys",
        transfer_name="OpenAI (ChatGPT API)",
        # **전에 여기 적어 둔 막힘은 사실이 아니었다.** "strict 모드가
        # minItems/maxItems 를 거부한다" 고 적었는데, 문서를 열어 보니 둘 다
        # 지원 목록에 있다. 읽지 않고 적은 것이 한 마일스톤을 막고 있었다.
        #
        # 실제로 갈리는 것은 추론 모델의 파라미터 둘이다 — `providers/openai.py`.
        note="gpt-5 계열은 temperature 를 못 바꾸고, 재시도에서 온도 손잡이를 잃는다",
    ),
    ProviderInfo(
        id=ANTHROPIC,
        label="Anthropic Claude",
        models=("claude-opus-5-5", "claude-sonnet-5-5"),
        needs_key=True,
        local_only=False,
        key_url="https://console.anthropic.com/settings/keys",
        transfer_name="Anthropic (Claude API)",
        # OpenAI 호환이 아니라는 것은 맞았다. 다만 **구조 강제 방식을 틀리게 적었다** —
        # 도구 호출이 아니라 `output_config.format` 이다.
        #
        # 그리고 적어 두지 않은 쪽이 더 컸다. `minItems` 는 0·1 만, `maxItems` 는
        # 아예 안 받는다 — 표현 개수 강제가 그대로는 400 이 된다 (04 §10).
        note="개수 제약을 와이어 스키마에 못 싣는다 — 응답을 받아서 다시 잰다",
    ),
)

BY_ID: dict[str, ProviderInfo] = {p.id: p for p in PROVIDERS}

# **실제 구현.** `ProviderInfo.implemented` 가 이 표를 읽는다 — 선언이 아니라 사실이다.
# 여기에 들어오면 고를 수 있게 되고, 그 전까지는 목록에 안 나온다.
IMPLEMENTATIONS: dict[str, type[LLMProvider]] = {
    LLAMA: LlamaServerProvider,
    GEMINI: GeminiProvider,
    OPENAI: OpenAIProvider,
    ANTHROPIC: AnthropicProvider,
}


def selectable(mode: str) -> tuple[ProviderInfo, ...]:
    """그 모드에서 **고를 수 있는** 제공자.

    `implemented` 가 아닌 것은 넣지 않는다 — 고를 수 있는데 안 되는 것은
    목록에 없는 것보다 나쁘다.
    """
    return tuple(
        p for p in PROVIDERS if p.implemented and (mode == "local" or not p.local_only)
    )


def default_for(mode: str) -> ProviderInfo:
    """회원이 아직 안 골랐을 때. 모드별로 전에 쓰던 것과 같게 둔다."""
    chosen = selectable(mode)
    if not chosen:
        raise RuntimeError(f"{mode} 모드에서 고를 수 있는 제공자가 없다")
    return chosen[0]


def info(provider_id: str) -> ProviderInfo | None:
    return BY_ID.get(provider_id)
