"""회원별 저장 데이터: 사용량 · 히스토리 · 나의 표현 · 연습 기록."""

from fastapi import APIRouter, Query

from app.config import get_settings
from app.db import AnalysisRecord, PracticeRecord, VocabularyItem
from app.deps import DbDep, SessionUser
from app.errors import NotFoundError
from app.schemas import (
    DeletionSummary,
    HistoryDetail,
    HistoryItem,
    PracticeHistoryItem,
    UsageResponse,
    VocabularyCreate,
    VocabularyItemOut,
    VocabularyRemoval,
)
from app.services import account, records, usage, vocabulary

router = APIRouter(prefix="/api", tags=["account"])


def _iso(value) -> str:
    return value.isoformat() if value else ""


@router.get("/usage", response_model=UsageResponse)
def get_usage(user: SessionUser, db: DbDep) -> UsageResponse:
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
def list_history(user: SessionUser, db: DbDep, limit: int = Query(30, ge=1, le=100)):
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
def get_history(record_id: int, user: SessionUser, db: DbDep) -> HistoryDetail:
    row = db.get(AnalysisRecord, record_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("기록을 찾을 수 없습니다.")
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
def delete_history(record_id: int, user: SessionUser, db: DbDep) -> dict:
    row = db.get(AnalysisRecord, record_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("기록을 찾을 수 없습니다.")
    db.delete(row)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------- 단어장


def _out(row: VocabularyItem, practice_count: int = 0) -> VocabularyItemOut:
    return VocabularyItemOut(
        id=row.id,
        expression=row.expression,
        type=row.type,
        meaning=row.meaning,
        example=row.example,
        example_ko=row.example_ko,
        source_text=row.source_text,
        created_at=_iso(row.created_at),
        practice_count=practice_count,
    )


@router.get("/vocabulary", response_model=list[VocabularyItemOut])
def list_vocabulary(user: SessionUser, db: DbDep):
    """나의 표현 전부. 분석 화면의 별도 이 목록으로 자기 상태를 안다."""
    rows = (
        db.query(VocabularyItem)
        .filter(VocabularyItem.user_id == user.id)
        .order_by(VocabularyItem.created_at.desc())
        .all()
    )
    counts = vocabulary.practice_counts(db, user.id)
    return [_out(r, counts.get(r.expression, 0)) for r in rows]


@router.post("/vocabulary", response_model=VocabularyItemOut)
def add_vocabulary(item: VocabularyCreate, user: SessionUser, db: DbDep) -> VocabularyItemOut:
    """나의 표현에 올린다. 분석 화면의 별이 부른다.

    여기서는 **덮어쓴다.** 별을 누르는 쪽은 방금 분석한 풍부한 값을 들고 오므로,
    전에 연습으로 자동 등록되며 비어 있던 칸이 이 기회에 채워져야 한다.
    """
    row = vocabulary.upsert(db, user.id, item.expression, item.model_dump(), overwrite=True)
    db.commit()
    counts = vocabulary.practice_counts(db, user.id)
    return _out(row, counts.get(row.expression, 0))


@router.delete("/vocabulary/{item_id}", response_model=VocabularyRemoval)
def delete_vocabulary(item_id: int, user: SessionUser, db: DbDep) -> VocabularyRemoval:
    """나의 표현에서 제외한다. **그 표현의 연습 기록도 함께 사라진다.**

    되돌릴 수 없다. 확인은 화면이 받는다 — API 는 묻지 않는다.
    왜 함께 지우는지는 `services/vocabulary.py`.
    """
    row = db.get(VocabularyItem, item_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("나의 표현에서 찾을 수 없습니다.")
    expression = row.expression
    deleted = vocabulary.remove(db, row)
    db.commit()
    return VocabularyRemoval(expression=expression, practices_deleted=deleted)


# --------------------------------------------------------------------- 연습 기록


@router.get("/practice/history", response_model=list[PracticeHistoryItem])
def list_practice(
    user: SessionUser,
    db: DbDep,
    limit: int = Query(50, ge=1, le=200),
    verdict: str | None = Query(default=None, description="다시 로 걸러 오답만 볼 수 있다"),
    expression: str | None = Query(default=None, description="한 표현의 기록만. 나의 표현이 쓴다"),
):
    query = db.query(PracticeRecord).filter(PracticeRecord.user_id == user.id)
    if verdict:
        query = query.filter(PracticeRecord.verdict == verdict)
    if expression:
        query = query.filter(PracticeRecord.expression == expression)
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


@router.get("/account/data", response_model=DeletionSummary)
def my_data_counts(user: SessionUser, db: DbDep) -> DeletionSummary:
    """내 데이터가 몇 건인지. 지우기 전에 무엇이 사라지는지 보여주려고 있다."""
    return DeletionSummary(**account.count_data(db, user.id))


@router.delete("/account/data", response_model=DeletionSummary)
def delete_my_data(user: SessionUser, db: DbDep) -> DeletionSummary:
    """내가 쌓은 기록을 전부 지운다. **계정은 남는다.**

    두 모드 공통이다 — 로컬에는 지울 계정이 없으므로 (09-mode-matrix.md §3.6).
    """
    deleted = account.purge_data(db, user.id)
    db.commit()
    return DeletionSummary(**deleted)
