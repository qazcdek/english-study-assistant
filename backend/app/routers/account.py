"""회원별 저장 데이터: 사용량 · 히스토리 · 나의 표현 · 연습 기록."""

from fastapi import APIRouter, Query

from app.config import get_settings
from app.db import AnalysisRecord, PracticeRecord, User, VocabularyItem
from app.deps import CipherDep, DbDep, SessionUser
from app.errors import AppError, NotFoundError
from app.providers import registry
from app.providers.gemini import verify_api_key
from app.schemas import (
    AccountSettings,
    ActiveModelRequest,
    ApiKeyRequest,
    DeletionSummary,
    HistoryDetail,
    HistoryItem,
    PracticeHistoryItem,
    TidySummary,
    UsageResponse,
    VocabularyCreate,
    VocabularyItemOut,
    VocabularyRemoval,
)
from app.services import account, history, keys, records, usage, vocabulary

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


# **고정 경로를 `{record_id}` 보다 먼저 선언한다.** 순서가 뒤면 `duplicates` 와
# `tidy` 가 기록 id 로 읽혀서 "기록을 찾을 수 없습니다" 가 된다 — 실제로 그랬다 (M2-T7).
@router.get("/history/duplicates", response_model=TidySummary)
def count_duplicates(user: SessionUser, db: DbDep) -> TidySummary:
    """정리하면 몇 건이 사라지나. **묻기 전에** 보여주는 데 쓴다."""
    return TidySummary(removed=len(history.duplicate_ids(db, user.id)))


@router.post("/history/tidy", response_model=TidySummary)
def tidy_history(user: SessionUser, db: DbDep) -> TidySummary:
    """같은 문단의 분석 기록에서 **최신 하나만** 남긴다.

    되돌릴 수 없다. 확인은 화면이 받는다 — API 는 묻지 않는다
    (03-api-spec.md 의 다른 삭제와 같은 규칙이다).
    """
    removed = history.tidy(db, user.id)
    db.commit()
    return TidySummary(removed=removed)


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


# ------------------------------------------- 제공자·모델 선택과 키 (두 모드)
#
# **cloud 전용인 `auth` 라우터에 두지 않는다.** 로컬도 제공자를 고를 수 있어야 하고
# (local 은 llama-server 와 cloud LLM 전부), 그러려면 키도 로컬에서 넣을 수 있어야 한다.
# 전에는 `auth` 에 있어서 **로컬에서는 Gemini 를 고를 수도 키를 넣을 수도 없었다** (M12-T4).


def _settings_of(db: DbDep, user: User) -> AccountSettings:
    settings = get_settings()
    choice = keys.resolve(user, settings.app_mode)
    return AccountSettings(
        active_provider=choice.provider.id,
        active_model=choice.model,
        keys=keys.providers_with_keys(db, user.id),
        ready=keys.has_key(db, user, choice),
    )


@router.get("/account/settings", response_model=AccountSettings)
def read_settings(user: SessionUser, db: DbDep) -> AccountSettings:
    """지금 무엇으로 일하나. 화면이 선택 UI 를 그리는 데 쓴다."""
    return _settings_of(db, user)


@router.put("/account/settings", response_model=AccountSettings)
def choose_model(
    request: ActiveModelRequest, user: SessionUser, db: DbDep
) -> AccountSettings:
    """쓸 제공자와 모델을 고른다 — **회원 전역 설정**이다.

    저장하는 순간부터 분석과 채점이 그것으로 간다. 고를 수 없는 것은 거부한다 —
    저장해 두고 나중에 기본값으로 떨어지면 회원은 자기가 고른 것으로 돌아간다고 믿는다.
    """
    mode = get_settings().app_mode
    allowed = {p.id: p for p in registry.selectable(mode)}
    provider = allowed.get(request.provider)
    if provider is None:
        raise AppError("이 모드에서 고를 수 없는 제공자입니다.")
    if request.model and request.model not in provider.models:
        raise AppError("그 제공자가 제공하지 않는 모델입니다.")

    user.active_provider = provider.id
    user.active_model = request.model or provider.models[0]
    db.commit()
    return _settings_of(db, user)


@router.put("/account/api-key", response_model=AccountSettings)
async def save_api_key(
    request: ApiKeyRequest, user: SessionUser, db: DbDep, cipher: CipherDep
) -> AccountSettings:
    """제공자별 키를 넣는다. 넣기 전에 실제로 쓸 수 있는지 한 번 확인한다."""
    settings = get_settings()
    provider_id = request.provider or keys.resolve(user, settings.app_mode).provider.id
    provider = registry.info(provider_id)
    if provider is None or not provider.implemented:
        raise AppError("지금 쓸 수 없는 제공자입니다.")
    if not provider.needs_key:
        raise AppError(f"{provider.label} 는 키가 필요하지 않습니다.")

    # 지금은 Gemini 하나뿐이다. 둘이 늘면 확인 방법도 제공자마다 갈린다 (M12-T3).
    if provider_id == registry.GEMINI:
        ok, detail = await verify_api_key(
            request.api_key,
            base_url=settings.gemini_base_url,
            model=provider.models[0],
        )
        if not ok:
            raise AppError(f"키를 확인하지 못했습니다. {detail or ''}".strip())

    keys.save(db, user.id, provider_id, request.api_key, cipher)
    db.commit()
    return _settings_of(db, user)


@router.delete("/account/api-key", response_model=AccountSettings)
def delete_api_key(user: SessionUser, db: DbDep, provider: str = "") -> AccountSettings:
    """키를 지운다. 제공자를 안 주면 지금 고른 것을 지운다."""
    provider_id = provider or keys.resolve(user, get_settings().app_mode).provider.id
    row = keys.row_for(db, user.id, provider_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return _settings_of(db, user)
