"""공용 글감을 읽는 길 (M13-T6).

### 키를 요구하지 않는다

`SessionUser` 다 — **신원만** 본다. 미리 분석은 이미 끝나 있으므로 이 경로는
LLM 을 부르지 않고, 그래서 동의·키·사용량과 아무 상관이 없다. 묶어 두면
`H-041` 이 다시 난다 — 키가 없는 회원에게서 **읽기까지 숨긴다.**

사용량도 세지 않는다. 세는 이유는 회원 각자의 LLM 한도를 쓰기 때문인데
(09 §3.3), 글감은 운영자 키로 미리 돈 것이다.

### 모드 분기를 두지 않는다

공용 글감은 cloud 전용이지만(09 §3.8) **여기에 `is_cloud` 를 적지 않는다.**
표는 두 모드에 다 있고 local 에서는 비어 있으므로, 같은 코드가 local 에서는
`article: null` 을 돌려준다. §3.8 이 고른 장치가 그것이다 — 분기 하나를 더
두는 대신 **데이터가 비어 있게 해서** 분기를 빼먹어도 local 에서 돌지 않는다.
탭을 감추는 것은 화면 쪽이 한다.

[문서] plan/DONE.md M13-T6
"""

from fastapi import APIRouter

from app.deps import DbDep, SessionUser
from app.errors import NotFoundError
from app.schemas import (
    ArticleOut,
    DailyArticleResponse,
    ParagraphAnalysisOut,
    ParagraphOut,
)
from app.services import articles, records

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("/current", response_model=DailyArticleResponse)
def current_article(_user: SessionUser, db: DbDep) -> DailyArticleResponse:
    """지금 보여줄 글감 한 편과 그 문단들. 고른 것이 없으면 `article: null`."""
    shown = articles.current(db)
    if shown is None:
        return DailyArticleResponse(article=None)

    row = shown.article
    return DailyArticleResponse(
        article=ArticleOut(
            id=row.id,
            source=row.source,
            url=row.url,
            title=row.title,
            section=row.section,
            published_at=row.published_at.isoformat() if row.published_at else "",
            picked_for=row.picked_for.isoformat() if row.picked_for else "",
            level=shown.level,
            paragraphs=[
                ParagraphOut(
                    ordinal=p.ordinal, text=p.text, prepared=p.ordinal in shown.prepared
                )
                for p in shown.paragraphs
            ],
        )
    )


@router.get("/{article_id}/paragraphs/{ordinal}", response_model=ParagraphAnalysisOut)
def paragraph_analysis(
    article_id: int, ordinal: int, _user: SessionUser, db: DbDep
) -> ParagraphAnalysisOut:
    """문단 하나의 미리 분석.

    **없는 문단과 아직 분석되지 않은 문단을 같은 404 로 답한다.** 구별해 주면
    회원이 할 수 있는 일이 달라지지 않는데(둘 다 "지금은 볼 수 없다") 글감에
    문단이 몇 개인지를 번호로 더듬어 알아낼 수 있게 된다. `current` 가 이미
    `prepared` 로 어느 문단이 준비됐는지 말해 주므로 화면도 손해가 없다.
    """
    row = articles.analysis(db, article_id, ordinal)
    if row is None:
        raise NotFoundError("아직 준비되지 않은 문단입니다.")
    return ParagraphAnalysisOut(
        ordinal=ordinal,
        level=row.level,
        # 프롬프트가 바뀌면 저장된 모양도 낡는다. 회원 기록과 **같은 자리에서** 올린다
        # (14 §3.5 는 공용 표에도 그대로 적용된다).
        result=records.upgrade(row.result),
        markdown=row.markdown,
        failed_parts=row.failed_parts or [],
        model=row.model,
    )
