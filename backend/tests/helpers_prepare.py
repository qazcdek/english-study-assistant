"""미리 분석 검사가 쓰는 세팅 (M13-T5).

`test_prepare.py` 밖으로 뺀 이유는 하나다 — `M13-T4`(고르기)와 `M13-T6`(화면)도
**같은 모양의 기사 한 편**을 세워야 한다. 각자 만들면 세 곳이 갈라지고, 갈라지면
한 곳만 고친 채로 통과한다.

`M13-T6` 이 실제로 그 자리에 왔다. 화면 검사는 **분석까지 들어간** 기사가 필요한데,
분석 행을 손으로 짜 넣으면 `prepare` 가 실제로 저장하는 모양과 갈라진다 — 그러면
화면이 못 읽는 형식을 넣어 두고 검사는 통과한다. 그래서 `run_prepare` 로
**진짜 경로를 돌린다.** 가짜인 것은 LLM 하나뿐이다.

문단은 **실제 길이로** 둔다. 50자 하한(`services/paragraphs.py`)을 넘겨야 쪼개기
경로와 같은 것을 먹이게 된다.
"""

from datetime import UTC, date, datetime

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

    **두 번 불러도 같은 사람이다.** 기사를 두 편 세우는 검사(`M13-T6`)가
    `make_article` 을 두 번 부르는데, 그때마다 운영자를 새로 만들면
    `users.google_sub` 의 유일 제약에 걸린다. 운영자는 어차피 한 명이다
    (`operator.find()` 가 첫 행을 집는다).
    """
    existing = operator.find(db)
    if existing is not None:
        return existing

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


def make_article(
    db: Session,
    cipher: KeyCipher,
    *,
    source_id: str = "world/2026/oct/22/example",
    picked_for: date | None = None,
) -> Article:
    """운영자 + 문단 세 개를 든 기사 한 편.

    `picked_for` 를 주지 않으면 **안 고른 후보**다 — 화면은 후보를 안 보여주므로
    (`services/articles.py`) 그 상태도 세울 수 있어야 한다.
    """
    operator_with_key(db, cipher)

    article = Article(
        source="guardian",
        source_id=source_id,
        url=f"https://www.theguardian.com/{source_id}",
        title="An example article",
        section="world",
        published_at=datetime(2026, 10, 22, 6, 0, tzinfo=UTC),
        picked_for=picked_for,
    )
    db.add(article)
    db.flush()

    for ordinal, text in enumerate(PARAGRAPHS, start=1):
        db.add(ArticleParagraph(article_id=article.id, ordinal=ordinal, text=text))
    db.commit()
    return article


async def run_prepare(db: Session, article: Article, monkeypatch, *, provider=None):
    """미리 분석을 **실제 경로로** 돌린다. 바꿔 끼우는 것은 프로바이더 하나뿐이다.

    `analyzer_for` 만 가로막는다 — 운영자 키를 복호화해 Gemini 를 만드는 그 한
    줄이 테스트에서 못 도는 유일한 부분이다. 나머지(파트 네 번 호출 · 마크다운 ·
    `records.stamp` · 문단마다 커밋)는 그대로 지나가므로, **저장된 모양이 화면이
    읽는 모양과 같은지**를 검사가 실제로 묻게 된다.
    """
    from app.config import get_settings
    from app.services import prepare
    from app.services.analyzer import AnalyzerService
    from tests.fake_provider import FakeProvider

    service = AnalyzerService(provider or FakeProvider())
    monkeypatch.setattr(prepare, "analyzer_for", lambda *a, **k: service)
    cipher = KeyCipher(get_settings().encryption_key)
    return await prepare.article(db, article, cipher, get_settings())
