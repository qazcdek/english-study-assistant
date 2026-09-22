"""분석 기록.

로컬은 혼자 쓰는 도구라 로그인이 없다. 시작할 때 만들어 둔 사용자 행 하나에 모두 매단다.
웹 배포판(main)의 `account.py` 와 스키마·응답 형태를 같게 두어, 두 갈래 사이에서
코드를 옮길 때 손볼 것을 줄인다.
"""

from fastapi import APIRouter, Query

from app.db import AnalysisRecord
from app.deps import DbDep, UserDep
from app.errors import AppError
from app.schemas import HistoryDetail, HistoryItem
from app.services import records

router = APIRouter(prefix="/api", tags=["history"])


def _iso(value) -> str:
    return value.isoformat() if value else ""


def _owned(record_id: int, user, db) -> AnalysisRecord:
    row = db.get(AnalysisRecord, record_id)
    if row is None or row.user_id != user.id:
        raise AppError("기록을 찾을 수 없습니다.")
    return row


@router.get("/history", response_model=list[HistoryItem])
def list_history(user: UserDep, db: DbDep, limit: int = Query(50, ge=1, le=200)):
    rows = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.user_id == user.id)
        .order_by(AnalysisRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        HistoryItem(
            id=r.id,
            source_text=r.source_text,
            level=r.level,
            created_at=_iso(r.created_at),
            failed_parts=r.failed_parts or [],
        )
        for r in rows
    ]


@router.get("/history/{record_id}", response_model=HistoryDetail)
def get_history(record_id: int, user: UserDep, db: DbDep) -> HistoryDetail:
    row = _owned(record_id, user, db)
    return HistoryDetail(
        id=row.id,
        source_text=row.source_text,
        level=row.level,
        created_at=_iso(row.created_at),
        failed_parts=row.failed_parts or [],
        # 프롬프트를 손볼 때마다 결과 스키마가 바뀐다. 옛 형식으로 저장된 기록을 올려서 넘긴다.
        result=records.upgrade(row.result),
        markdown=row.markdown,
    )


@router.delete("/history/{record_id}")
def delete_history(record_id: int, user: UserDep, db: DbDep) -> dict:
    db.delete(_owned(record_id, user, db))
    db.commit()
    return {"ok": True}
