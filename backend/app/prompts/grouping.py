"""문단을 주제 단위로 묶을 **경계**를 모델에게 묻는다 (M13-T11).

### 글을 돌려받지 않는다. 번호만 받는다

모델이 묶은 **글**을 돌려주게 하면 한 문장을 다듬거나 빠뜨릴 수 있다. 그러면
가디언 기자 이름을 붙여 **남의 글을 고쳐서 그 사람 이름으로 내보내는** 셈이다
(`M13-T10` 이 약관에 따라 크레딧을 요구하는 것과 정면으로 어긋난다). 학습 자료로서도
원문이 아닌 것을 읽히게 된다.

그래서 **각 묶음이 시작하는 자리 번호**만 받는다. 본문은 우리가 원문에서 이어
붙이므로 **한 글자도 바뀌지 않는다.** 그리고 번호는 검사할 수 있다 — 0에서
시작하는지, 오름차순인지, 범위 안인지, 묶음이 입력 상한을 넘지 않는지.

### 못 믿을 답은 버리고 단어 예산으로 떨어진다

검사를 통과하지 못하면 `paragraphs.group()` 의 단어 예산 묶기를 쓴다. 그러면
**이 호출이 실패해도 그날 글감이 사라지지 않는다** — 주제 경계는 더 나은 것이고
없어도 되는 것이다.

[문서] plan/DONE.md M13-T11
"""

from app.prompts.models import variant_for
from app.providers.base import ChatMessage

#: 목표 낱말 수. 프롬프트에 적지만 **강제는 코드가 한다** — 모델이 어기면 버린다.
TARGET_WORDS = 120

SYSTEM = """너는 영어 기사를 학습용으로 손질하는 편집자다.

{output_rules}

번호가 붙은 토막들을 **읽는 단위로 묶는다.** 토막 하나가 한 문장일 때가 많아서,
그대로 두면 한 문장씩 따로 읽히게 된다.

규칙
- 각 묶음이 **시작하는 토막 번호**만 `starts` 배열에 담는다. 첫 번째는 반드시 0 이다.
- 번호는 **오름차순**이고 겹치지 않는다. 묶음은 **이어진 토막들**이다 —
  순서를 바꾸거나 중간을 건너뛰지 않는다.
- 같은 화제·같은 장면을 말하는 토막을 한 묶음으로 둔다. 화제가 바뀌는 자리,
  인물이 바뀌는 자리, 인용이 시작되거나 끝나는 자리가 경계다.
- 한 묶음이 **{target} 낱말 안팎**이 되게 한다. 한 묶음에 토막 하나만 두는 것은
  그 토막이 혼자 그만큼 길 때뿐이다.
- **글을 쓰지 않는다.** 번호만 돌려준다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "starts": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 1,
        }
    },
    "required": ["starts"],
    "additionalProperties": False,
}


def build_messages(texts: list[str], *, model: str = "") -> list[ChatMessage]:
    """번호 붙인 토막을 보여주고 경계를 묻는다.

    낱말 수를 함께 적어 준다 — 모델이 "{target} 낱말 안팎" 을 맞추려면 세어야 하고,
    세는 일을 모델에게 시키면 틀린다.
    """
    lines = []
    for index, text in enumerate(texts):
        lines.append(f"[{index}] ({len(text.split())}낱말) {text}")
    return [
        ChatMessage(
            role="system",
            content=SYSTEM.format(
                output_rules=variant_for(model).output_rules, target=TARGET_WORDS
            ),
        ),
        ChatMessage(role="user", content="\n\n".join(lines)),
    ]
