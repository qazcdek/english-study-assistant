"""나의 표현(`vocabulary`) 과 연습 기록(`practices`) 을 묶는 규칙.

**연습 기록은 나의 표현을 통해서만 닿을 수 있다.** 목록 화면이 유일한 입구이므로,
나의 표현에 없는 표현의 연습 기록은 **아무 화면에도 나타나지 않는다.** 그래서 둘을
따로 두면 안 된다 — 연습하면 자동으로 올라가고, 제외하면 기록도 함께 사라진다.

같은 종류의 버그를 이미 한 번 겪었다. 예문이 비면 체크박스까지 사라져 작문 연습
입구가 통째로 없어졌는데, 데이터는 멀쩡했고 **닿을 길만 없었다** (H-019).

이 묶음을 클라이언트에 맡기지 않는다. 채점과 등록을 두 번 호출하게 하면 뒤쪽이
실패하는 순간 **입구 없는 연습 기록**이 생기고, 그건 사용자 눈에 안 보이므로
아무도 고치지 않는다. 한 트랜잭션에서 함께 한다.

표현 문자열이 둘을 잇는 열쇠다 (`practices.expression` ↔ `vocabulary.expression`).
외래키를 안 쓴 이유는 **연습 기록이 먼저 쌓여 있었기 때문**이다 — 운영 DB 에 이미
있는 행들을 옮겨 붙여야 하고, 그 과정에서 짝을 못 찾는 행을 버리게 된다.
`unique(user_id, expression)` 이 이미 걸려 있어 이 쌍은 자연키로 충분하다.

[문서] 03-api-spec.md 왜 연습 기록이 함께 사라지나
[문서] 06-practice.md §3
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import PracticeRecord, VocabularyItem

# 연습이 자동으로 올릴 때 채우는 칸. 나머지는 분석 화면의 별이 채운다.
FROM_PRACTICE = ("type", "meaning", "example", "example_ko", "source_text")


def upsert(
    db: Session,
    user_id: int,
    expression: str,
    values: dict[str, str],
    *,
    overwrite: bool,
) -> VocabularyItem:
    """나의 표현에 올린다. 이미 있으면 같은 행을 쓴다.

    `overwrite=False` 는 **빈 칸만 채운다.** 연습이 자동으로 올릴 때 쓴다 —
    별로 담아 둔 풍부한 행을 연습 요청의 빈 값으로 덮어쓰면 안 된다.
    """
    row = (
        db.query(VocabularyItem)
        .filter(VocabularyItem.user_id == user_id, VocabularyItem.expression == expression)
        .one_or_none()
    )
    if row is None:
        row = VocabularyItem(user_id=user_id, expression=expression)
        db.add(row)
    for field in FROM_PRACTICE:
        incoming = values.get(field, "")
        if overwrite or (incoming and not getattr(row, field)):
            setattr(row, field, incoming)
    return row


def practice_counts(db: Session, user_id: int) -> dict[str, int]:
    """표현별 연습 횟수. 목록을 그릴 때 한 번에 가져온다 — 행마다 세면 N+1 이 된다."""
    rows = (
        db.query(PracticeRecord.expression, func.count(PracticeRecord.id))
        .filter(PracticeRecord.user_id == user_id)
        .group_by(PracticeRecord.expression)
        .all()
    )
    return {expression: count for expression, count in rows}


def remove(db: Session, row: VocabularyItem) -> int:
    """나의 표현에서 제외한다. **그 표현의 연습 기록도 함께 지운다.**

    남겨 두면 어느 화면에도 안 나타나는 유령 데이터가 된다. 사라진다는 사실은
    화면이 먼저 묻는다 — API 는 묻지 않는다 (03-api-spec.md).
    """
    deleted = (
        db.query(PracticeRecord)
        .filter(
            PracticeRecord.user_id == row.user_id,
            PracticeRecord.expression == row.expression,
        )
        .delete(synchronize_session=False)
    )
    db.delete(row)
    return deleted
