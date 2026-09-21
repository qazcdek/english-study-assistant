"""일 단위 사용량 집계와 한도.

회원 본인 키를 쓰더라도, 실수나 오작동으로 그 사람의 하루 한도가 한꺼번에 날아가는 일은
막아야 한다. Gemini 무료 등급은 모델별로 하루 요청 수가 정해져 있고,
분석 한 번이 LLM 호출 네 번이라 금방 소진된다.
"""

from datetime import UTC, date
from datetime import datetime as dt

from sqlalchemy.orm import Session

from app.db import UsageCounter, User
from app.errors import UsageLimitError


def today() -> date:
    return dt.now(UTC).date()


def _counter(db: Session, user: User) -> UsageCounter:
    day = today()
    counter = (
        db.query(UsageCounter)
        .filter(UsageCounter.user_id == user.id, UsageCounter.day == day)
        .one_or_none()
    )
    if counter is None:
        counter = UsageCounter(user_id=user.id, day=day)
        db.add(counter)
        db.flush()
    return counter


def snapshot(db: Session, user: User) -> UsageCounter:
    return _counter(db, user)


def check_and_increment(
    db: Session, user: User, *, kind: str, limit: int, llm_calls: int = 1
) -> UsageCounter:
    """한도를 확인하고 통과하면 바로 올린다.

    호출 전에 올리는 이유는, 실패한 호출도 회원의 API 한도를 소모하기 때문이다.
    """
    counter = _counter(db, user)
    used = getattr(counter, kind)
    if used >= limit:
        raise UsageLimitError(f"오늘 {kind} {used}/{limit} 를 사용했습니다.")

    setattr(counter, kind, used + 1)
    counter.llm_calls += llm_calls
    db.commit()
    return counter
