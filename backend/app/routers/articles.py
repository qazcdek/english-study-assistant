"""공용 뉴스를 읽는 길 (M13-T6).

### 키를 요구하지 않는다

`SessionUser` 다 — **신원만** 본다. 미리 분석은 이미 끝나 있으므로 이 경로는
LLM 을 부르지 않고, 그래서 동의·키·사용량과 아무 상관이 없다. 묶어 두면
`H-041` 이 다시 난다 — 키가 없는 회원에게서 **읽기까지 숨긴다.**

사용량도 세지 않는다. 세는 이유는 회원 각자의 LLM 한도를 쓰기 때문인데
(09 §3.3), 뉴스는 운영자 키로 미리 돈 것이다.

### 읽는 요청이 **방아쇠**다

오늘 뉴스가 온전하지 않으면 고르기를 `BackgroundTasks` 로 던지고 **기다리지 않고**
어제 것을 돌려준다 (`09 §3.8`). 고르기+분석은 문단 수만큼 LLM 호출이라 수십 초다 —
응답 경로에서 돌리면 **첫 방문자가 그 시간을 전부 기다린다.**

시계에 걸 수 없어서 이렇게 한다. cron 도 상주 프로세스도 Render 무료 티어에서는
못 믿는다(15분 미사용이면 잠든다). 판단 자체는 `daily.should_run` 이 들고, 여기서는
**부르기만** 한다 — 그 판단을 라우터 안에 두면 검사가 HTTP 를 떠야만 물을 수 있다.

### 모드 분기를 두지 않는다

공용 뉴스는 cloud 전용이지만(09 §3.8) **여기에 `is_cloud` 를 적지 않는다.**
표는 두 모드에 다 있고 local 에서는 비어 있으므로, 같은 코드가 local 에서는
`article: null` 을 돌려준다. §3.8 이 고른 장치가 그것이다 — 분기 하나를 더
두는 대신 **데이터가 비어 있게 해서** 분기를 빼먹어도 local 에서 돌지 않는다.
탭을 감추는 것은 화면 쪽이 한다.

[문서] plan/DONE.md M13-T6
"""

from fastapi import APIRouter, BackgroundTasks

from app.deps import DbDep, OperatorUser, SessionUser, SettingsDep
from app.errors import NotFoundError
from app.schemas import (
    ArticleListResponse,
    ArticleOut,
    DailyArticleResponse,
    ParagraphAnalysisOut,
    ParagraphOut,
)
from app.services import articles, daily, records

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("/current", response_model=DailyArticleResponse)
def current_article(
    _user: SessionUser,
    db: DbDep,
    tasks: BackgroundTasks,
    settings: SettingsDep,
) -> DailyArticleResponse:
    """지금 보여줄 뉴스 한 편과 그 문단들. 고른 것이 없으면 `article: null`.

    오늘 것이 아직 없으면 **뒤에서 고르기를 시작하고 어제 것을 돌려준다.**
    """
    if daily.should_run(db, settings):
        # **암호 도구를 의존성으로 받지 않는다.** `CipherDep` 은 `ENCRYPTION_KEY` 가
        # 없으면 거부하므로(`deps.get_cipher`) 그걸 여기 걸면 **llama-server 만 쓰는
        # local 에서 읽기 경로가 막힌다.** 실제로 그렇게 짰다가 검사가 400 으로 잡았다.
        # 키가 필요한 자리는 분석 하나뿐이고, 거긴 cloud 에서만 닿는다.
        tasks.add_task(daily.run, settings)

    shown = articles.current(db)
    if shown is None:
        return DailyArticleResponse(article=None)
    return DailyArticleResponse(article=_out(shown))


@router.get("/picked", response_model=ArticleListResponse)
def picked_articles(_user: OperatorUser, db: DbDep) -> ArticleListResponse:
    """그동안 고른 뉴스를 **최신순으로.** 운영자만 볼 수 있다 (M13-T13).

    **회원은 오늘 것만 본다.** 지난 뉴스를 쌓아 보여주는 것은 운영자가 품질을
    훑는 도구이고, 회원 화면은 "하루 한 편" 이 전제다 (`01` · `09 §3.8`).

    `current` 에 분기를 더하지 않은 이유는 **다른 물음**이기 때문이다 — 섞으면
    응답 모양이 회원마다 달라져 화면이 둘을 다 그려야 한다.
    """
    return ArticleListResponse(articles=[_out(s) for s in articles.picked(db)])


def _out(shown: articles.Shown) -> ArticleOut:
    """`Shown` 을 응답 모양으로. **한 곳에서만 옮긴다** — 두 경로가 같은 것을 쓴다."""
    row = shown.article
    return ArticleOut(
        id=row.id,
        source=row.source,
        url=row.url,
        title=row.title,
        byline=row.byline,
        section=row.section,
        published_at=row.published_at.isoformat() if row.published_at else "",
        picked_for=row.picked_for.isoformat() if row.picked_for else "",
        paragraphs=[
            ParagraphOut(ordinal=p.ordinal, text=p.text, prepared=p.ordinal in shown.prepared)
            for p in shown.paragraphs
        ],
    )


@router.get("/{article_id}/paragraphs/{ordinal}", response_model=ParagraphAnalysisOut)
def paragraph_analysis(
    article_id: int, ordinal: int, _user: SessionUser, db: DbDep
) -> ParagraphAnalysisOut:
    """문단 하나의 미리 분석.

    **없는 문단과 아직 분석되지 않은 문단을 같은 404 로 답한다.** 구별해 주면
    회원이 할 수 있는 일이 달라지지 않는데(둘 다 "지금은 볼 수 없다") 뉴스에
    문단이 몇 개인지를 번호로 더듬어 알아낼 수 있게 된다. `current` 가 이미
    `prepared` 로 어느 문단이 준비됐는지 말해 주므로 화면도 손해가 없다.
    """
    row = articles.analysis(db, article_id, ordinal)
    if row is None:
        raise NotFoundError("아직 준비되지 않은 문단입니다.")
    return ParagraphAnalysisOut(
        ordinal=ordinal,
        # 프롬프트가 바뀌면 저장된 모양도 낡는다. 회원 기록과 **같은 자리에서** 올린다
        # (14 §3.5 는 공용 표에도 그대로 적용된다).
        result=records.upgrade(row.result),
        markdown=row.markdown,
        failed_parts=row.failed_parts or [],
        model=row.model,
    )
