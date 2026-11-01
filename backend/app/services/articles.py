"""골라 온 기사 한 편을 공용 표에 앉힌다 (M13-T8).

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

[문서] plan/DONE.md M13-T8
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.db import Article, ArticleParagraph
from app.errors import ArticleBodyError
from app.services import paragraphs


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
