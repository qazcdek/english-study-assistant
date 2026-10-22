"""모델 계열에 따라 **길들이기 지시**를 고른다.

### 가르는 선

프롬프트에는 두 종류가 섞여 있다.

```
교육 내용      표현 유형 일곱 · 난이도 기준 · 칸별 명세 · 스키마
              → 모델과 무관하다.  analysis.py 에 **한 곳만** 둔다
길들이기       JSON 만 내라 · 끝없이 재검토하지 말라 · 재시도 문구
              → 모델마다 다르다.  여기서 **계열별로** 둔다
```

이 선이 이 파일의 전부다. 전에는 둘이 `SHARED_SYSTEM` 한 덩이에 섞여 있었다.

### 왜 계열별로 두나

프롬프트는 **Qwen3-27B 로 다듬은 것**이다. `example` 생략이 Qwen3 에서는 안 드러나고
Gemini 에서만 터졌다(H-021) — 같은 지시가 같게 먹지 않는다. 그래서 한쪽을 고치려면
다른 쪽을 깨뜨릴 위험을 안고 고쳐야 했고, 그게 `H-005`~`H-010` 을 막아 왔다.

"끝없이 재검토하지 말라" 는 Qwen3 의 사고 모드 때문에 들어간 문장이다. Gemini 에
그 문장이 필요한지는 **아직 모른다.** 모르는 채로 한 덩이에 두면 한쪽을 위한 처방이
다른 쪽에 조용히 적용된다.

### 지금은 넷이 같다

**갈라짐은 사고가 아니라 결정으로만 일어나야 한다.** 그래서 지금은 모든 계열이 같은
문구를 들고, `test_model_prompts.py` 가 **같은지 검사한다.** 실측(M3-T1)이 차이를
보여주면 그때 그 검사를 고치면서 갈린다 — 검사를 고치는 일이 곧 결정의 기록이다.
"""

from dataclasses import dataclass

# 모델 이름에서 알아보는 계열. 이름이 바뀌어도 계열은 유지되므로 분기 키로 쓴다.
GEMINI = "gemini"
LLAMA = "llama"
OPENAI = "openai"
CLAUDE = "claude"
# 알아보지 못한 모델. **추측을 끼얹지 않고** 기본 문구를 쓴다.
UNKNOWN = "unknown"

_MARKS: tuple[tuple[str, str], ...] = (
    (GEMINI, "gemini"),
    (CLAUDE, "claude"),
    (OPENAI, "gpt"),
    (OPENAI, "o1"),
    (OPENAI, "o3"),
    (LLAMA, "qwen"),
    (LLAMA, "llama"),
    (LLAMA, "local-model"),  # llama-server 가 모델명을 무시할 때 쓰는 기본값
)


def family_of(model: str) -> str:
    """모델 이름 → 계열.

    정확한 이름이 아니라 **계열**로 가른다. `gemini-3.5-flash-lite` 가 `gemini-4` 가
    되어도 분기는 유지되어야 한다 — 버전마다 키를 두면 모델을 올릴 때마다 조용히
    기본값으로 떨어진다.
    """
    lowered = model.lower()
    for family, mark in _MARKS:
        if mark in lowered:
            return family
    return UNKNOWN


# 출력 규율. **교육 내용을 여기 적지 않는다** — 표현 유형이나 난이도 기준이 여기
# 들어오면 계열마다 복사되고, 그때부터 갈라진다 (11-docs-architecture.md §2.1).
_OUTPUT_RULES = """공통 규칙:
- JSON 외의 텍스트, 인사말, 코드 펜스(```)를 절대 덧붙이지 않는다.
- 영어는 영어로, 설명은 모두 한국어로 쓴다.
- 설명은 "~이다 / ~한다" 체로 쓴다. "~입니다 / ~합니다" 체를 섞지 않는다.
- 확실하지 않은 정보는 지어내지 말고, 해당 항목을 빼거나 배열을 비운다.
- 정해진 개수 안에서 끝낸다. 후보를 끝없이 재검토하지 말고 판단이 서면 바로 출력한다."""

# 작문 연습 쪽 출력 규율. 분석보다 짧다 — 개수 제약이 없기 때문이다.
_PRACTICE_RULES = """공통 규칙:
- JSON 외의 텍스트, 인사말, 코드 펜스(```)를 절대 덧붙이지 않는다.
- 설명은 한국어로, "~이다 / ~한다" 체로 쓴다. "~입니다 / ~합니다" 체를 섞지 않는다."""

_RETRY_NUDGE = (
    "직전 응답이 올바른 JSON이 아니었다. 이번에는 설명이나 코드 펜스 없이 "
    "스키마를 따르는 JSON 객체 하나만 출력하라."
)


@dataclass(frozen=True)
class Variant:
    """한 계열에 쓰는 길들이기 지시."""

    family: str
    output_rules: str
    practice_rules: str
    retry_nudge: str


# 계열별 묶음. **지금은 내용이 전부 같다** — 그게 검사로 고정되어 있다.
VARIANTS: dict[str, Variant] = {
    family: Variant(
        family=family,
        output_rules=_OUTPUT_RULES,
        practice_rules=_PRACTICE_RULES,
        retry_nudge=_RETRY_NUDGE,
    )
    for family in (GEMINI, LLAMA, OPENAI, CLAUDE, UNKNOWN)
}


def variant_for(model: str) -> Variant:
    """그 모델에 쓸 묶음. 모르는 모델이면 기본값이다."""
    return VARIANTS[family_of(model)]
