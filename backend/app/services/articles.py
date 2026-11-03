"""공용 글감 — 표에 **앉히고**(M13-T8), 화면에 **읽어 준다**(M13-T6).

둘을 한 파일에 둔 이유는 같은 표 셋을 쥐기 때문이다 — `articles` ·
`article_paragraphs` · `paragraph_analyses`. 넣는 규칙과 읽는 규칙이 갈리면
**손으로 넣어 확인한 것이 화면에서는 안 맞는다.**

## 앉히는 쪽

**가져오는 쪽과 가르는 자리다.** 지금 글감이 들어오는 길은 손(`tools/article.py`)
하나뿐이고, 가디언에서 골라 오는 쪽은 아직 없다 (`M13-T4`). 두 길이 하는 일 중
**같은 것은 여기 있다** — 본문 HTML 을 문단으로 쪼개 `articles` 와
`article_paragraphs` 에 넣는 것. 이걸 도구 쪽에 두면 `M13-T4` 가 같은 코드를 다시
쓰게 되고, 둘이 갈라지면 손으로 넣어 확인한 것이 자동 경로에서는 안 맞는다.

### 몇 번 넣어도 같다

`(source, source_id)` 가 유일하므로 같은 기사를 다시 넣으면 **행을 새로 만들지 않고
그 행을 쓴다.** 문단도 다시 넣지 않는다 — 문단 id 에 분석이 붙어 있어서
(`paragraph_analyses.paragraph_id`), 지우고 새로 넣으면 **수십 번의 LLM 호출이
날아간다.** 그래서 본문이 바뀌어도 이미 있는 문단을 고치지 않는다. 다시 쪼개야
한다면 기사를 지우는 것이 맞고, 그건 분석을 버리기로 **결정하는** 일이다.

### 고른 날은 덮어쓴다

문단과 반대다. `picked_for` 는 "어느 날의 글감인가" 이고 **같은 기사를 다른 날의
글감으로 다시 쓸 수 있다.** 비싼 것은 분석이고 그건 문단에 붙어 있으므로, 날짜를
바꿔도 아무것도 버려지지 않는다.

## 읽는 쪽

### 왜 "오늘" 을 여기서 따지지 않나

`09-mode-matrix.md §3.8` 이 규정한다 — **오늘 것이 없으면 그동안 어제 것을
보여준다.** 그러므로 보여주는 쪽이 할 일은 날짜를 따지는 것이
아니라 **가장 최근에 고른 한 편을 꺼내는 것**이고, 며칠 글감인지는 `picked_for`
를 그대로 화면에 찍어 회원이 읽게 한다.

이렇게 두면 **"오늘" 이 어느 시간대인가**(`M13-T4` 의 미해결 결정)를 이 쪽이
선점하지 않는다. 고르는 쪽이 UTC 로 정하든 KST 로 정하든 화면은 적힌 날짜를
읽을 뿐이다.

### 안 고른 후보는 내려주지 않는다

`M13-T4` 는 후보 여러 편을 앉히고 그중 하나만 고른다 — `picked_for` 가 비어 있는
행은 후보다. **그걸 id 로 열 수 있게 두면 우리가 고르지 않은 기사의 전문이 회원에게
간다.** 출처 약관을 어디까지 받아들일지가 아직 안 끝났으므로(`M13-T7`) 문을 좁게
둔다.

### 난이도는 묻지 않는다. 준비된 것을 준다

`paragraph_analyses` 는 난이도마다 한 행이지만 미리 분석은 **중급 하나만** 돌린다
(`prepare.JOB_LEVEL` — 셋을 다 채우면 호출이 세 배다). 그래서 **회원이 고른
난이도를 받지 않는다** — 받아 놓고 없는 것을 찾으면 빈 화면이 되고, 조용히 중급을
돌려주면 화면이 거짓말을 한다. 어느 난이도인지를 **응답에 실어** 화면이 적게 한다.

질의마다 `level` 을 끼우는 것은 그 하나뿐이라서가 아니다. 안 끼우면 난이도가
둘이 되는 날 **같은 문단에 행이 둘**이 되어 `one_or_none()` 이 500 을 던진다.

### 분석이 "있다" 의 기준은 행이 있는지다

파트 하나가 실패한 행도 **보여준다** — 그 기준은 `M13-T4` 에서 이미 갈라 두었다.
건너뛰기(재시도 대상인가)는 `failed_parts` 가 비어 있을 때만이고, 보여주기는
행이 있으면 된다. 한 파트가 고집스럽게 실패하면 그날 글감이 아예 안 나오는 쪽이
더 나쁘다. 화면은 `failed_parts` 를 받아 빈 자리를 표시한다.

[문서] plan/DONE.md M13-T6
[문서] plan/DONE.md M13-T8
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.db import Article, ArticleParagraph, ParagraphAnalysis
from app.errors import ArticleBodyError
from app.services import paragraphs, prepare


@dataclass(frozen=True)
class Draft:
    """표에 앉히기 전의 기사 한 편. **본문은 아직 HTML 이다.**"""

    source: str
    source_id: str
    url: str
    title: str
    section: str
    published_at: datetime
    body: str


@dataclass
class Stored:
    """앉힌 결과.

    **`created` 를 따로 센다.** 문단 수만 보면 "새로 넣었다" 와 "이미 있던 것을
    그대로 썼다" 가 구별되지 않는다 — 손으로 두 번 넣었을 때 조용히 같은 숫자가 난다.
    """

    article: Article
    paragraphs: int
    created: bool


def store(db: Session, draft: Draft, *, picked_for: date | None = None) -> Stored:
    """기사와 문단을 넣는다. **몇 번 불러도 같다** — 이유는 머리말."""
    texts = paragraphs.split(draft.body)
    if not texts:
        raise ArticleBodyError(detail=f"{draft.source}/{draft.source_id}")

    row = (
        db.query(Article)
        .filter(Article.source == draft.source, Article.source_id == draft.source_id)
        .one_or_none()
    )
    created = row is None
    if row is None:
        row = Article(
            source=draft.source,
            source_id=draft.source_id,
            url=draft.url,
            title=draft.title,
            section=draft.section,
            published_at=draft.published_at,
        )
        db.add(row)
        db.flush()

    if picked_for is not None:
        row.picked_for = picked_for

    stored = (
        db.query(ArticleParagraph).filter(ArticleParagraph.article_id == row.id).count()
    )
    if stored == 0:
        for ordinal, text in enumerate(texts, start=1):
            db.add(ArticleParagraph(article_id=row.id, ordinal=ordinal, text=text))
        stored = len(texts)

    db.commit()
    return Stored(article=row, paragraphs=stored, created=created)


@dataclass(frozen=True)
class Shown:
    """화면 한 번을 그리는 데 필요한 것 전부. **본문까지, 분석은 빼고.**

    분석을 같이 담지 않는 이유는 값이다 — 한 편을 통째로 보내면 128KB 이고
    (실측: `result` 49KB + `markdown` 82KB), 난이도 셋을 채우면 세 배가 된다.
    읽는 흐름도 한 문단씩이므로 펼칠 때 하나만 가져온다.
    """

    article: Article
    paragraphs: list[ArticleParagraph]
    #: 분석 행이 있는 문단의 `ordinal`. 미리 분석이 중간에 멈췄으면 뒤쪽이 빈다.
    prepared: frozenset[int]
    #: 그 분석이 어느 난이도로 준비됐나. 화면이 이것을 적는다.
    level: str


def current(db: Session) -> Shown | None:
    """지금 보여줄 글감. 고른 것이 하나도 없으면 `None`.

    **`None` 은 오류가 아니다.** 첫 배포 직후와 고르기가 실패하고 있는 동안의
    정상 상태다 — 라우터가 404 로 바꾸지 않는 이유가 그것이다.
    """
    article = (
        db.query(Article)
        .filter(Article.picked_for.isnot(None))
        # 날짜가 같은 두 편이 있을 수 있다 — `uq_article_day_source` 가 하루에
        # **출처당** 한 편까지 허용한다(영·미 한 곳씩). 그때 어느 쪽을 보여줄지는
        # 아직 결정이 아니므로 **나중에 앉힌 것**으로 둔다. 손으로 다시 넣으면
        # 새로 넣은 것이 보이는 쪽이 눈으로 확인하기 쉽다.
        .order_by(Article.picked_for.desc(), Article.id.desc())
        .first()
    )
    if article is None:
        return None

    rows = (
        db.query(ArticleParagraph)
        .filter(ArticleParagraph.article_id == article.id)
        .order_by(ArticleParagraph.ordinal)
        .all()
    )
    # 분석 본문(`result`·`markdown`)을 끌고 오지 않는다. 있는지만 센다.
    prepared = {
        ordinal
        for (ordinal,) in db.query(ArticleParagraph.ordinal)
        .join(ParagraphAnalysis, ParagraphAnalysis.paragraph_id == ArticleParagraph.id)
        .filter(
            ArticleParagraph.article_id == article.id,
            ParagraphAnalysis.level == prepare.JOB_LEVEL,
        )
        .all()
    }
    return Shown(
        article=article,
        paragraphs=rows,
        prepared=frozenset(prepared),
        level=prepare.JOB_LEVEL,
    )


def analysis(db: Session, article_id: int, ordinal: int) -> ParagraphAnalysis | None:
    """문단 하나의 미리 분석. 없으면 `None` — 라우터가 404 로 바꾼다.

    **`article_id` 를 질의에 끼운다.** `ordinal` 만으로 찾으면 다른 기사의 같은
    번호 문단이 걸린다. 그리고 `picked_for` 를 함께 보므로 **안 고른 후보의
    문단은 번호를 맞혀도 열리지 않는다.**
    """
    return (
        db.query(ParagraphAnalysis)
        .join(ArticleParagraph, ParagraphAnalysis.paragraph_id == ArticleParagraph.id)
        .join(Article, ArticleParagraph.article_id == Article.id)
        .filter(
            Article.id == article_id,
            Article.picked_for.isnot(None),
            ArticleParagraph.ordinal == ordinal,
            ParagraphAnalysis.level == prepare.JOB_LEVEL,
        )
        .one_or_none()
    )
