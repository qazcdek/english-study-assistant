"""하루 한 편을 고르고 미리 분석한다 (M13-T4).

가져오는 쪽은 `guardian.py`, 앉히는 쪽은 `articles.store`, 분석은 `prepare.article`
이다. **여기 있는 것은 "언제 도나" 와 "어느 것을 고르나" 둘이다.**

### 시계에 걸지 않는다. 요청이 방아쇠다

```
요청이 들어온다
  오늘 뉴스가 온전한가?
    그렇다  →  그걸 보여준다
    아니다  →  고르기+분석을 뒤로 던지고, **그동안 어제 것을 보여준다**
```

cron 도 상주 프로세스도 쓸 수 없다. local 은 내 PC 라 꺼져 있고, cloud 는 Render
무료 티어라 **15분 미사용이면 잠든다** (`M3-T3`). 어느 쪽도 스케줄러를 못 믿는다.
**늦게 도는 것은 괜찮다** — 하루에 한 번만 성공하면 되고, 그 전까지는 어제 것이
빈 화면을 막는다 (`09 §3.8`).

### "오늘" 은 한국 날짜이고, 새벽 6시에 넘어간다

`picked_for` 는 시점이 아니라 **"며칠의 뉴스인가" 라는 이름표**다. 읽는 사람이
한국에 있으므로 화면의 "11월 4일 뉴스" 이 그 사람의 오늘과 맞아야 한다. UTC 로
세면 **매일 오전 9시에 뉴스가 바뀐다** — 실제로 `M13-T8` 의 도구가 UTC 기본값을
써서 한국 시간 11월 2일에 넣은 기사가 11월 1일 뉴스로 찍혔다.

그리고 **자정이 아니라 새벽 6시에 끊는다.** 자정에 바꾸면 밤늦게 읽던 사람이
글을 잃는다 — 23시 50분에 읽던 글이 10분 뒤에 어제 것이 된다. 6시로 밀면 밤
공부는 같은 글로 끝나고 **새벽 공부는 그 시각부터 새 글을 받는다.**

표의 다른 시각은 UTC 그대로다(`published_at` 은 출처가 준 값이다). **둘을 같은
시간대로 둘 이유가 없다** — 하나는 시점이고 하나는 이름표다.

### 두 관문이 local 에서 이 기능을 끈다

모드 분기를 적지 않는다 (`09 §3.8` 의 장치). 대신 **순서가 그 일을 한다** —
운영자가 없으면 가디언을 치기도 전에 멈춘다. local 부트스트랩 사용자에게는
`is_operator` 를 켜지 않으므로(`operator.py`) `find()` 가 `None` 이고, 그러면
local 의 `.env` 에 가디언 키가 있어도 **한 번도 호출하지 않는다.**

### 부분 실패는 "안 된 것" 으로 센다

"완료됐나" 를 열로 들지 않는다. **문단마다 분석이 온전한지 센다** — 열을 두면
실제 상태와 어긋날 수 있지만 세는 쪽은 언제나 맞다. 그리고 기준이 둘로 갈린다
(`09 §3.8`):

```
다시 돌릴까   행이 없거나 failed_parts 가 남아 있으면 → 돈다
보여줄까      행이 있으면 (부분이라도) → 보여준다
```

**행이 있는지로만 보면 안 된다.** 세 파트만 성공한 행이 "이미 됐음" 으로 읽혀
총평이 영영 빈 문단이 **모든 회원에게 고정된다.**

[문서] plan/DONE.md M13-T15
[문서] plan/DONE.md M13-T4
"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.crypto import KeyCipher
from app.config import Settings
from app.db import (
    Article,
    ArticleParagraph,
    ParagraphAnalysis,
    PickAttempt,
    session_scope,
)
from app.errors import AppError, ArticleBodyError
from app.providers.base import LLMProvider
from app.services import articles, grouping, guardian, operator, prepare

log = logging.getLogger(__name__)

#: 읽는 사람의 시간대. `picked_for` 가 이 날짜로 찍힌다 — 이유는 머리말.
KST = timedelta(hours=9)

#: **하루가 시작하는 시각 (한국 시간).** 자정이 아니라 새벽 6시다.
#:
#: 자정에 바꾸면 **밤늦게 읽던 사람이 글을 잃는다** — 23시 50분에 읽던 글이 10분
#: 뒤에 어제 것이 되고, 펼쳐 둔 문단이 바뀐다. 6시로 밀면 밤 공부는 같은 글로
#: 끝나고, **새벽에 일찍 공부하는 사람은 그 시각 이후에 새 글을 받는다.**
#:
#: 사람이 쓰는 "오늘" 에 맞춘 값이므로 시간대와 따로 둔다 — `KST` 는 어디에 있나,
#: 이것은 하루를 어디서 끊나다.
DAY_STARTS_AT = timedelta(hours=6)

#: 실패하고 나서 쉬는 시간. **설정값으로 두지 않는다** — 바꿀 이유가 생기면 그때
#: 꺼낸다. 하루 최대 288번이고, 가져오기 단계 실패는 LLM 을 안 불러 싸다.
COOLDOWN = timedelta(minutes=5)


def today(now: datetime | None = None) -> date:
    """"며칠의 뉴스인가" 의 오늘. **한국 날짜이고 새벽 6시에 넘어간다.**

    한국 시간 새벽 5시 59분은 아직 **어제**다 — `DAY_STARTS_AT` 가 그 이유를 든다.

    `now` 를 받는 이유는 검사다. 안 받으면 검사가 식을 **옮겨 적어** 확인하게 되고,
    그러면 이 함수를 UTC 로 되돌려도 검사가 통과한다 — 실제로 그렇게 짰다가
    깨뜨려 보고 알았다.
    """
    return ((now or datetime.now(UTC)) + KST - DAY_STARTS_AT).date()


def incomplete(db: Session, day: date) -> bool:
    """그날 뉴스가 **없거나 온전하지 않은가.** 돌릴 이유가 있는지를 이것으로 본다."""
    article = (
        db.query(Article)
        .filter(Article.picked_for == day)
        .order_by(Article.id.desc())
        .first()
    )
    if article is None:
        return True

    paragraphs = (
        db.query(func.count(ArticleParagraph.id))
        .filter(ArticleParagraph.article_id == article.id)
        .scalar()
        or 0
    )
    # **`failed_parts` 가 빈 행만 센다.** 부분 실패한 행을 "됐음" 으로 읽으면
    # 빈 파트가 모든 회원에게 고정된다.
    #
    # **비교를 SQL 로 보내지 않는다.** `failed_parts == []` 로 적었더니 SQLite 는
    # 통과하고 **Postgres 가 거부했다** — `json` 타입에는 `=` 연산자가 없다
    # (`H-032` 의 엔진 차이). 문단은 기껏해야 수십 개라 파이썬에서 센다.
    rows = (
        db.query(ParagraphAnalysis.failed_parts)
        .join(ArticleParagraph, ParagraphAnalysis.paragraph_id == ArticleParagraph.id)
        .filter(ArticleParagraph.article_id == article.id)
        .all()
    )
    done = sum(1 for (failed,) in rows if not failed)
    return paragraphs == 0 or done < paragraphs


def stale(db: Session, day: date) -> int | None:
    """그날 기사가 **낡은 파이프라인으로 만들어졌나.** 낡았으면 그 기사 id.

    문단 묶음이나 발췌 범위가 바뀌면 이미 앉힌 기사는 그 전 규칙으로 선 것이다.
    `store()` 는 **문단을 다시 쪼개지 않으므로**(분석이 문단 id 에 붙어 있다) 다시
    앉혀도 안 바뀐다 — 그래서 **버리고 다시 받는 길**이 따로 있어야 한다.

    **추측하지 않는다.** 문단 수나 글자 수로 낡음을 재면 경계에 걸린 멀쩡한 기사를
    버린다. `articles.PIPELINE` 은 우리가 규칙을 바꿀 때만 올라간다.

    **오늘 것만 본다.** 지난 기사까지 다시 받으면 하루에 수십 편 × 스무 번
    호출이고, 운영자 목록의 지난 기사는 그때의 기록으로 남는 것이 맞다.
    """
    row = (
        db.query(Article.id, Article.pipeline)
        .filter(Article.picked_for == day)
        .order_by(Article.id.desc())
        .first()
    )
    if row is None:
        return None
    article_id, pipeline = row
    return article_id if pipeline < articles.PIPELINE else None


def resting(db: Session, day: date, *, now: datetime | None = None) -> bool:
    """쿨다운 중인가. 마지막 실패로부터 `COOLDOWN` 이 안 지났으면 참."""
    row = (
        db.query(PickAttempt)
        .filter(PickAttempt.picked_for == day, PickAttempt.source == "guardian")
        .one_or_none()
    )
    if row is None:
        return False
    now = now or datetime.now(UTC)
    failed_at = row.failed_at
    if failed_at.tzinfo is None:  # SQLite 는 시간대를 안 들고 돌려준다
        failed_at = failed_at.replace(tzinfo=UTC)
    return now - failed_at < COOLDOWN


def should_run(db: Session, settings: Settings, *, day: date | None = None) -> bool:
    """지금 고르기를 던질까. **관문 넷을 순서대로** 본다 — 싼 것이 앞이다.

    운영자 확인이 가디언 호출보다 **앞에** 있는 것이 local 에서 이 기능을 끄는
    장치다 (머리말).
    """
    if not settings.guardian_api_key:
        return False
    if operator.find(db) is None:
        return False
    day = day or today()
    # **낡은 기사는 온전해도 다시 받는다** (M13-T15). `incomplete` 만 보면 구버전이
    # 온전한 채로 영원히 남아 새 규칙이 적용되지 않는다 — 사용자가 그걸로 막혔다.
    if not incomplete(db, day) and stale(db, day) is None:
        return False
    return not resting(db, day)


async def run(settings: Settings, *, day: date | None = None) -> None:
    """고르고 분석한다. **자기 세션을 연다** — 요청 응답이 이미 나갔다.

    아무것도 밖으로 던지지 않는다. 실패는 쿨다운 표에 적히고, 다음 요청이 5분 뒤에
    다시 시도한다. **응답 경로가 아니므로 올릴 곳이 없다.**

    **암호 도구를 받지 않고 여기서 만든다.** 의존성으로 받으면 `ENCRYPTION_KEY` 가
    없는 local 에서 **읽기 경로까지** 막힌다 (`deps.get_cipher` 가 거부한다).
    """
    day = day or today()
    cipher = KeyCipher(settings.encryption_key)

    # **오늘 고른 것이 있으면 다시 고르지 않는다.** 분석이 중간에 멈춰 재시도로
    # 들어온 경우가 그렇다 — `prepare` 가 끝난 문단을 건너뛰므로 **이어서** 돈다.
    # 이걸 안 두면 재시도마다 가디언을 다시 치고, 1위는 이미 쓴 기사라 넘어가며
    # 2위를 앉히려다 `uq_article_day_source` 에 걸린다. 실제 응답으로 돌려 보고
    # 발견한 자리다.
    with session_scope() as db:
        # **낡은 것은 먼저 버린다.** 남겨 두면 `_todays()` 가 그것을 찾아 분석만
        # 이어 돌고, 문단은 영원히 구버전으로 남는다.
        doomed = stale(db, day)
        if doomed is not None:
            articles.discard(db, doomed)
            log.info("낡은 파이프라인의 기사를 버렸다: #%s", doomed)
        target = _todays(db, day)

    if target is None:
        try:
            drafts = await guardian.candidates(settings)
        except AppError as exc:
            with session_scope() as db:
                _note(db, day, f"{exc.code}: {exc.detail or exc.message}")
            return

        with session_scope() as db:
            # 문단 묶기가 쓸 프로바이더. **없으면 단어 예산으로 묶인다** — 주제
            # 경계는 더 나은 것이고 없어도 되는 것이다 (`services/grouping.py`).
            try:
                provider = prepare.provider_for(db, cipher, settings)
            except AppError:
                provider = None
            try:
                target = await _pick(db, drafts, day, provider)
            except AppError as exc:
                _note(db, day, f"{exc.code}: {exc.detail or exc.message}")
                return
            finally:
                if provider is not None:
                    await provider.aclose()

    # **분석은 세션을 따로 쓴다.** 문단마다 커밋하며 몇 분을 돌므로(`prepare`)
    # 고르기와 한 트랜잭션에 묶으면 그 사이 다른 요청이 오늘 뉴스를 못 읽는다.
    with session_scope() as db:
        row = db.get(Article, target)
        if row is None:  # 그 사이 지워졌다 — 다음 요청이 다시 고른다
            return
        try:
            report = await prepare.article(db, row, cipher, settings)
        except AppError as exc:
            _note(db, day, f"{exc.code}: {exc.detail or exc.message}")
            return
        if report.stopped_at is not None:
            # 기사와 거기까지의 분석은 남는다. **5분 뒤 재시도가 이어서 돈다** —
            # 끝난 문단은 건너뛰므로 처음부터 다시 돌지 않는다.
            _note(db, day, f"{report.stopped_at}번 문단에서 네 파트가 전부 실패")


def _todays(db: Session, day: date) -> int | None:
    """그날 이미 고른 기사의 id. 없으면 `None`.

    `current()` 와 달리 **그 날짜만** 본다 — 어제 것으로 오늘을 때우지 않는다.
    """
    return (
        db.query(Article.id)
        .filter(Article.picked_for == day)
        .order_by(Article.id.desc())
        .scalar()
    )


async def _pick(
    db: Session,
    drafts: list[articles.Draft],
    day: date,
    provider: LLMProvider | None = None,
) -> int:
    """후보를 인기 순서대로 앉혀 본다. 성공한 기사의 id.

    **관문을 `store()` 가 든다.** 분량(`M13-T9`)과 크레딧(`M13-T10`)과 쪼개기
    (`M13-T3`)를 여기서 다시 보지 않는다 — 손으로 넣는 길과 **같은 문**을 지나야
    손으로 확인한 것을 자동 경로에서도 믿을 수 있다. 셋 다 `ArticleBodyError` 의
    자손이므로 **하나만 잡아도 빼먹을 수 없다.**
    """
    for draft in drafts:
        # **이미 뉴스로 쓴 기사는 넘긴다.** `store()` 는 `picked_for` 를 덮어쓰므로
        # (그 자리에서는 맞는 동작이다 — 비싼 것은 분석이고 문단에 붙어 있다) 걸러
        # 주지 않으면 어제 보여준 기사가 오늘 다시 1위일 때 **같은 글이 또 온다.**
        used = (
            db.query(Article.picked_for)
            .filter(
                Article.source == draft.source,
                Article.source_id == draft.source_id,
                Article.picked_for.isnot(None),
            )
            .scalar()
        )
        if used is not None:
            continue
        # **관문을 먼저 지나고 나서 묶는다** (M13-T11). 묶기가 LLM 을 부르므로
        # 못 쓸 기사에까지 호출을 쓰면 낭비다 — `gates()` 가 DB 를 안 타는 이유다.
        try:
            texts, cut = articles.gates(draft)
        except ArticleBodyError:
            continue  # 쪼개지지 않거나 · 500단어 토막이 없거나 · 크레딧이 없다

        groups = await grouping.by_topic(texts[cut.start : cut.stop], provider)
        try:
            stored = articles.store(db, draft, picked_for=day, groups=groups)
        except IntegrityError:
            # `uq_article_day_source` 다 — **다른 요청이 먼저 앉혔다.** 제약이 그대로
            # 잠금 역할을 한다(동시 요청을 막는 장치가 따로 없는 이유다). 실패가
            # 아니므로 쿨다운을 적지 않고, 그 기사를 그대로 쓴다.
            db.rollback()
            winner = (
                db.query(Article)
                .filter(Article.picked_for == day, Article.source == draft.source)
                .one_or_none()
            )
            if winner is not None:
                return winner.id
            continue
        return stored.article.id

    raise ArticleBodyError(detail=f"후보 {len(drafts)}개가 모두 관문을 통과하지 못했다")


def _note(db: Session, day: date, reason: str) -> None:
    """실패를 적는다. `(날짜, 출처)` 마다 한 줄이고 **횟수를 누적한다.**"""
    row = (
        db.query(PickAttempt)
        .filter(PickAttempt.picked_for == day, PickAttempt.source == "guardian")
        .one_or_none()
    )
    if row is None:
        row = PickAttempt(picked_for=day, source="guardian", failures=0)
        db.add(row)
    row.failed_at = datetime.now(UTC)
    row.failures += 1
    row.reason = reason[:500]
