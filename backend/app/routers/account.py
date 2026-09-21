"""회원별 저장 데이터: 사용량 · 히스토리 · 단어장 · 연습 기록."""

from fastapi import APIRouter, Query

from app.config import get_settings
from app.db import AnalysisRecord, PracticeRecord, VocabularyItem
from app.deps import DbDep, UserDep
from app.errors import AppError
from app.schemas import (
    HistoryDetail,
    HistoryItem,
    PracticeHistoryItem,
    UsageResponse,
    VocabularyCreate,
    VocabularyItemOut,
)
from app.services import usage

router = APIRouter(prefix="/api", tags=["account"])


def _iso(value) -> str:
    return value.isoformat() if value else ""


@router.get("/usage", response_model=UsageResponse)
def get_usage(user: UserDep, db: DbDep) -> UsageResponse:
    settings = get_settings()
    counter = usage.snapshot(db, user)
    db.commit()
    return UsageResponse(
        day=counter.day.isoformat(),
        analyses=counter.analyses,
        practices=counter.practices,
        analysis_limit=settings.daily_analysis_limit,
        practice_limit=settings.daily_practice_limit,
    )


# --------------------------------------------------------------------- 히스토리


@router.get("/history", response_model=list[HistoryItem])
def list_history(user: UserDep, db: DbDep, limit: int = Query(30, ge=1, le=100)):
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
    row = db.get(AnalysisRecord, record_id)
    if row is None or row.user_id != user.id:
        raise AppError("기록을 찾을 수 없습니다.")
    return HistoryDetail(
        id=row.id,
        source_text=row.source_text,
        level=row.level,
        created_at=_iso(row.created_at),
        failed_parts=row.failed_parts or [],
        result=row.result,
        markdown=row.markdown,
    )


@router.delete("/history/{record_id}")
def delete_history(record_id: int, user: UserDep, db: DbDep) -> dict:
    row = db.get(AnalysisRecord, record_id)
    if row is None or row.user_id != user.id:
        raise AppError("기록을 찾을 수 없습니다.")
    db.delete(row)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------- 단어장


@router.get("/vocabulary", response_model=list[VocabularyItemOut])
def list_vocabulary(user: UserDep, db: DbDep):
    rows = (
        db.query(VocabularyItem)
        .filter(VocabularyItem.user_id == user.id)
        .order_by(VocabularyItem.created_at.desc())
        .all()
    )
    return [
        VocabularyItemOut(
            id=r.id,
            expression=r.expression,
            type=r.type,
            meaning=r.meaning,
            example=r.example,
            example_ko=r.example_ko,
            source_text=r.source_text,
            created_at=_iso(r.created_at),
        )
        for r in rows
    ]


@router.post("/vocabulary", response_model=VocabularyItemOut)
def add_vocabulary(item: VocabularyCreate, user: UserDep, db: DbDep) -> VocabularyItemOut:
    existing = (
        db.query(VocabularyItem)
        .filter(
            VocabularyItem.user_id == user.id,
            VocabularyItem.expression == item.expression,
        )
        .one_or_none()
    )
    row = existing or VocabularyItem(user_id=user.id, expression=item.expression)
    row.type = item.type
    row.meaning = item.meaning
    row.example = item.example
    row.example_ko = item.example_ko
    row.source_text = item.source_text
    if existing is None:
        db.add(row)
    db.commit()
    return VocabularyItemOut(
        id=row.id,
        expression=row.expression,
        type=row.type,
        meaning=row.meaning,
        example=row.example,
        example_ko=row.example_ko,
        source_text=row.source_text,
        created_at=_iso(row.created_at),
    )


@router.delete("/vocabulary/{item_id}")
def delete_vocabulary(item_id: int, user: UserDep, db: DbDep) -> dict:
    row = db.get(VocabularyItem, item_id)
    if row is None or row.user_id != user.id:
        raise AppError("단어장 항목을 찾을 수 없습니다.")
    db.delete(row)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------- 연습 기록


@router.get("/practice/history", response_model=list[PracticeHistoryItem])
def list_practice(
    user: UserDep,
    db: DbDep,
    limit: int = Query(50, ge=1, le=200),
    verdict: str | None = Query(default=None, description="다시 로 걸러 오답만 볼 수 있다"),
):
    query = db.query(PracticeRecord).filter(PracticeRecord.user_id == user.id)
    if verdict:
        query = query.filter(PracticeRecord.verdict == verdict)
    rows = query.order_by(PracticeRecord.created_at.desc()).limit(limit).all()
    return [
        PracticeHistoryItem(
            id=r.id,
            expression=r.expression,
            prompt_ko=r.prompt_ko,
            model_answer=r.model_answer,
            learner_answer=r.learner_answer,
            verdict=r.verdict,
            uses_target=r.uses_target,
            feedback=r.feedback,
            created_at=_iso(r.created_at),
        )
        for r in rows
    ]
