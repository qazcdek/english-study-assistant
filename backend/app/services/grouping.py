"""문단을 주제 단위로 묶는다 — 모델에게 **경계만** 묻고 못 믿으면 버린다 (M13-T11).

왜 글이 아니라 번호인지는 `prompts/grouping.py` 머리말. 여기 있는 것은 **받은
번호를 믿을지 판단하는 규칙**이다.

### 통과시키는 조건 넷

```
0 에서 시작한다            첫 묶음이 첫 토막부터여야 빠진 글이 없다
오름차순이고 중복이 없다    아니면 묶음이 겹치거나 순서가 뒤집힌다
전부 범위 안이다            없는 번호를 가리키면 글이 사라진다
묶음이 상한을 안 넘는다      넘으면 회원 입력 상한과 같은 벽에 부딪힌다
```

하나라도 어긋나면 **단어 예산 묶기로 떨어진다.** 고치려 들지 않는다 — 번호를
손보기 시작하면 "모델이 고른 경계" 가 아니라 우리가 추측한 경계가 되고, 그걸
믿을 근거가 없다.

### 실패가 글감을 없애지 않는다

이 호출이 터져도 `fallback` 이 돌아 글감은 나온다. 주제 경계는 **더 나은 것이고
없어도 되는 것**이다 — 그래서 여기서 예외를 밖으로 던지지 않는다.

[문서] plan/DONE.md M13-T11
"""

import json
import logging
from itertools import pairwise

from app.prompts import grouping as prompts
from app.providers.base import LLMProvider
from app.providers.schema import adapt
from app.services import paragraphs

log = logging.getLogger(__name__)

#: 한 묶음이 넘어서는 안 되는 낱말 수. 목표(`GROUP_WORDS`)보다 넉넉하게 두되
#: **cloud 입력 상한(1200자)에 닿기 전에** 막는다 — 실측에서 120낱말이 761자였다.
MAX_WORDS = 180


def valid(starts: list[int], texts: list[str]) -> bool:
    """받은 경계를 쓸 수 있나. 조건 넷은 머리말."""
    if not starts or starts[0] != 0:
        return False
    if any(b <= a for a, b in pairwise(starts)):
        return False
    if any(not 0 <= s < len(texts) for s in starts):
        return False
    return all(
        sum(paragraphs.words(t) for t in texts[a:b]) <= MAX_WORDS
        for a, b in zip(starts, [*starts[1:], len(texts)], strict=False)
    )


def spans(starts: list[int], count: int) -> list[list[int]]:
    """경계를 `paragraphs.group()` 과 **같은 모양**(묶음별 자리 번호)으로 바꾼다."""
    ends = [*starts[1:], count]
    return [list(range(a, b)) for a, b in zip(starts, ends, strict=False)]


async def by_topic(
    texts: list[str], provider: LLMProvider | None = None
) -> list[list[int]]:
    """주제 단위 묶음. **못 믿으면 단어 예산 묶기를 돌려준다.**

    `provider` 가 없으면 아예 묻지 않는다 — local 처럼 운영자 키가 없는 자리에서
    이 함수를 불러도 안전해야 한다.
    """
    fallback = paragraphs.group(texts)
    if provider is None or len(texts) < 2:
        return fallback

    try:
        completion = await provider.complete(
            prompts.build_messages(texts, model=provider.model),
            json_schema=adapt(prompts.SCHEMA, provider.schema_limits),
        )
        starts = json.loads(completion.text)["starts"]
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 묶기를 막지 않는다
        log.warning("주제 경계를 못 받았다, 단어 예산으로 묶는다: %s", type(exc).__name__)
        return fallback

    if not isinstance(starts, list) or not all(isinstance(s, int) for s in starts):
        log.warning("주제 경계의 모양이 아니다, 단어 예산으로 묶는다")
        return fallback
    if not valid(starts, texts):
        log.warning("주제 경계가 검사를 통과하지 못했다: %s", starts)
        return fallback

    return spans(starts, len(texts))
