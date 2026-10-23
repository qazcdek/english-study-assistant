"""미리 분석 검사가 쓰는 세팅 (M13-T5).

`test_prepare.py` 밖으로 뺀 이유는 하나다 — `M13-T4`(고르기)와 `M13-T6`(화면)도
**같은 모양의 기사 한 편**을 세워야 한다. 각자 만들면 세 곳이 갈라지고, 갈라지면
한 곳만 고친 채로 통과한다.

문단은 **실제 길이로** 둔다. 50자 하한(`services/paragraphs.py`)을 넘겨야 쪼개기
경로와 같은 것을 먹이게 된다.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.auth.crypto import KeyCipher
from app.db import Article, ArticleParagraph, User
from app.services import keys, operator

PARAGRAPHS = (
    (
        "It's unlikely to find its way across the pond, but the idea has already "
        "taken hold in two of the largest markets in Europe."
    ),
    (
        "The committee stopped short of recommending a ban, saying the evidence "
        "was too thin to justify one at this stage."
    ),
    (
        "Supporters argue that the measure would pay for itself within a decade, "
        "a claim the treasury has neither endorsed nor disputed."
    ),
)


def operator_with_key(
    db: Session, cipher: KeyCipher, *, active_provider: str = "gemini"
) -> User:
    """공용 글감을 만들 수 있는 상태의 운영자.

    `active_provider` 를 다르게 줄 수 있다 — **활성 선택을 따르지 않는다**는 것을
    확인하려면 일부러 어긋나게 세워야 한다.
    """
    owner = User(
        google_sub="op",
        email=operator.OPERATOR_EMAIL,
        is_operator=True,
        active_provider=active_provider,
    )
    db.add(owner)
    db.flush()
    keys.save(db, owner.id, operator.JOB_PROVIDER, "AIzaSyFAKEKEY0000", cipher)
    db.commit()
    return owner


def make_article(db: Session, cipher: KeyCipher) -> Article:
    """운영자 + 문단 세 개를 든 기사 한 편."""
    operator_with_key(db, cipher)

    article = Article(
        source="guardian",
        source_id="world/2026/oct/22/example",
        url="https://www.theguardian.com/world/2026/oct/22/example",
        title="An example article",
        section="world",
        published_at=datetime(2026, 10, 22, 6, 0, tzinfo=UTC),
    )
    db.add(article)
    db.flush()

    for ordinal, text in enumerate(PARAGRAPHS, start=1):
        db.add(ArticleParagraph(article_id=article.id, ordinal=ordinal, text=text))
    db.commit()
    return article
