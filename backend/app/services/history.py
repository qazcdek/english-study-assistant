"""분석 기록 정리.

같은 문단을 여러 번 분석하면 기록이 그만큼 쌓인다. 목록에서 **같은 줄이 반복되어**
정작 다른 기록이 밀려 내려간다. 중복은 **최신 하나만** 남긴다.

### 무엇을 "같은 문단" 으로 보나

**공백 문자를 다 지운 결과가 같으면 중복이다** (사용자가 정한 규칙).

글자가 똑같은 것만 묶으면 모자라다. 같은 문단을 다시 붙여 넣을 때 끝에 줄바꿈이
붙거나 빠지고, 줄바꿈 위치가 달라지고, 들여쓰기가 섞인다 — 사람 눈에는 같은데
기계는 다르게 본다. 공백은 **문단의 내용이 아니므로** 아예 없애고 비교한다.

처음에는 공백을 "하나로 모으는" 선에서 멈췄는데, 그러면 줄바꿈 위치가 다른 같은
문단이 여전히 안 묶인다.

**대소문자와 문장부호는 건드리지 않는다.** `The cat` 과 `the cat` 은 다른 문단으로
본다. 영어 학습 도구이므로 그 차이가 공부의 대상이고, 묶어 버리면 **지우는 쪽이
틀린다.** 지우는 일에서는 덜 묶는 쪽이 안전하다.

[문서] 03-api-spec.md 기록 정리
[문서] plan/DONE.md M2-T7
"""

import re

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import AnalysisRecord

_SPACES = re.compile(r"\s+")


def same_paragraph(text: str) -> str:
    """묶음 열쇠. **공백 문자를 다 지운다.** 나머지는 그대로 둔다."""
    return _SPACES.sub("", text)


def duplicate_ids(db: Session, user_id: int) -> list[int]:
    """지워질 기록의 id. **최신 하나는 남는다.**

    고르는 일과 지우는 일을 나눠 둔 이유는, 지우기 전에 **몇 건인지 셀 수 있어야**
    하기 때문이다.
    """
    rows = (
        db.query(AnalysisRecord.id, AnalysisRecord.source_text)
        .filter(AnalysisRecord.user_id == user_id)
        # 최신이 먼저 오게 한다. id 로 한 번 더 가르는 이유는 같은 시각에 들어온
        # 기록이 있을 수 있어서다 — 그때도 **같은 것이 남아야** 한다.
        .order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id.desc())
        .all()
    )

    seen: set[str] = set()
    doomed: list[int] = []
    for record_id, text in rows:
        key = same_paragraph(text or "")
        if key in seen:
            doomed.append(record_id)
        else:
            seen.add(key)
    return doomed


def tidy(db: Session, user_id: int) -> int:
    """오래된 중복을 지우고 몇 건을 지웠는지 돌려준다."""
    doomed = duplicate_ids(db, user_id)
    if not doomed:
        return 0
    db.execute(
        delete(AnalysisRecord).where(
            AnalysisRecord.user_id == user_id,
            AnalysisRecord.id.in_(doomed),
        )
    )
    return len(doomed)
