"""회원 데이터와 계정 삭제.

개인정보 관점에서 **지우는 수단이 먼저**다. 모으는 기능만 있고 지우는 수단이 없으면
회원은 자기 데이터를 회수할 방법이 없다.

**FK 의 `ON DELETE CASCADE` 에 기대지 않고 표마다 명시적으로 지운다.** SQLite 는
`PRAGMA foreign_keys` 가 꺼져 있으면 CASCADE 가 동작하지 않는다. 테스트는 SQLite 로
도므로, 기대면 **테스트는 통과하고 Postgres 에서만 다르게 도는** 상태가 된다.

[문서] 14-data-layer.md §2
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import (
    AnalysisRecord,
    PracticeRecord,
    ProviderKey,
    UsageCounter,
    User,
    VocabularyItem,
)

# **지우는 범위가 둘이다.** 한 상수로 겸하려다 실제로 틀렸다 —
# `ProviderKey` 를 넣으니 "기록 전부 삭제" 가 **등록한 키까지 지웠다.** 회원은 학습
# 기록을 비우려 했는데 키를 잃고, 그다음 분석이 403 으로 막힌다 (M12-T2).
#
# 기록 삭제   회원이 쌓은 **학습 기록**만. 계정과 키는 남는다
# 탈퇴        매달린 것 **전부**. 키도 함께 사라진다 (07 §10 의 방침이 그렇게 적혀 있다)
RECORDS = (AnalysisRecord, PracticeRecord, VocabularyItem, UsageCounter)
# 회원에게 매달린 표 전부. 새 표를 만들면 여기에 더한다 —
# 빠뜨리면 탈퇴한 회원의 데이터가 남는다 (14-data-layer.md §3.4).
OWNED = (*RECORDS, ProviderKey)


def count_data(db: Session, user_id: int) -> dict[str, int]:
    """지워질 것이 몇 건인지. 화면이 확인 문구에 쓴다.

    **기록만 센다.** 이 숫자는 "기록 전부 삭제" 가 지울 것을 보여주는 용도이고,
    키는 거기서 지워지지 않는다.
    """
    return {
        model.__tablename__: db.scalar(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )
        or 0
        for model in RECORDS
    }


def purge_data(db: Session, user_id: int) -> dict[str, int]:
    """회원이 쌓은 기록을 전부 지운다. **계정은 남는다.**

    로컬 모드에는 지울 계정이 없으므로(사용자 행 하나를 앱이 만들어 둔다)
    두 모드가 공유할 수 있는 동작은 이것뿐이다.
    """
    return {
        model.__tablename__: db.execute(delete(model).where(model.user_id == user_id)).rowcount
        for model in RECORDS
    }


def delete_account(db: Session, user_id: int) -> dict[str, int]:
    """탈퇴. 기록을 지우고 계정 행까지 지운다.

    ORM 의 `delete(user)` 가 아니라 문장을 바로 던진다 — 위에서 bulk delete 로 자식을
    이미 지웠으므로 세션이 들고 있는 관계가 낡아 있다.
    """
    deleted = purge_data(db, user_id)
    # 기록 밖의 것 — 지금은 제공자 키다. 이것도 지워야 탈퇴가 끝난다.
    for model in set(OWNED) - set(RECORDS):
        db.execute(delete(model).where(model.user_id == user_id))
    db.expire_all()
    db.execute(delete(User).where(User.id == user_id))
    return deleted
