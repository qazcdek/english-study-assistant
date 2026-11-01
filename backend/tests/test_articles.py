"""골라 온 기사를 공용 표에 앉힌다 (M13-T8).

규약은 `app/services/articles.py` 머리말. 여기서 지키는 것은 셋이다.

- **몇 번 넣어도 같다** — 기사 행도 문단도 두 벌이 되지 않는다
- **이미 있는 문단은 고치지 않는다** — 문단 id 에 분석이 붙어 있다
- **쪼개지지 않는 본문은 거부한다** — 문단 0개는 "다 됐다" 로 읽힌다

쪼개기 규칙 자체는 `test_paragraphs.py` 가 든다. 여기서는 **그 규칙을 타는지**만 본다.
"""

from datetime import UTC, date, datetime

import pytest

from app.db import Article, ArticleParagraph, session_scope
from app.errors import ArticleBodyError
from app.services import articles

BODY = (
    "<p>Ukraine has resumed its attacks on Russian oil refineries in defiance "
    "of pressure from Washington, officials said on Sunday.</p>"
    "<aside><p>Related: an earlier report on the refinery strikes in October</p></aside>"
    "<p>Short line.</p>"
    "<p>The committee stopped short of recommending a ban, saying the evidence "
    "was too thin to justify one at this stage of the inquiry.</p>"
)


def draft(**over) -> articles.Draft:
    base = {
        "source": "guardian",
        "source_id": "world/2026/nov/01/example",
        "url": "https://www.theguardian.com/world/2026/nov/01/example",
        "title": "An example article",
        "section": "world",
        "published_at": datetime(2026, 11, 1, 17, 20, tzinfo=UTC),
        "body": BODY,
    }
    return articles.Draft(**{**base, **over})


def test_the_body_becomes_numbered_paragraphs_in_order(cloud):
    """**쪼개기 규칙을 그대로 탄다** — 추천 블록과 짧은 줄은 문단이 아니다."""
    with session_scope() as db:
        stored = articles.store(db, draft())

        assert stored.created is True
        assert stored.paragraphs == 2  # aside 하나 · 50자 미만 하나가 빠진다

        rows = (
            db.query(ArticleParagraph)
            .order_by(ArticleParagraph.ordinal)
            .all()
        )
        assert [r.ordinal for r in rows] == [1, 2]
        assert rows[0].text.startswith("Ukraine has resumed")
        assert rows[1].text.startswith("The committee stopped short")
        assert "Related:" not in " ".join(r.text for r in rows)


def test_storing_the_same_article_twice_does_not_double_anything(cloud):
    """`(source, source_id)` 가 유일하다. **다시 넣는 것이 안전해야** 손으로 고칠 수 있다."""
    with session_scope() as db:
        first = articles.store(db, draft())
        second = articles.store(db, draft())

        assert second.created is False
        assert second.article.id == first.article.id
        assert db.query(Article).count() == 1
        assert db.query(ArticleParagraph).count() == 2


def test_an_already_stored_article_keeps_its_paragraphs_even_if_the_body_changed(cloud):
    """**문단 id 에 분석이 붙어 있다.** 다시 쪼개면 수십 번의 호출이 날아간다."""
    with session_scope() as db:
        articles.store(db, draft())
        kept = db.query(ArticleParagraph).order_by(ArticleParagraph.ordinal).first()
        kept_id, kept_text = kept.id, kept.text

        articles.store(db, draft(body=BODY.replace("Ukraine", "Finland")))

        again = db.query(ArticleParagraph).order_by(ArticleParagraph.ordinal).first()
        assert (again.id, again.text) == (kept_id, kept_text)


def test_the_picked_day_is_overwritten_because_nothing_expensive_hangs_on_it(cloud):
    """문단과 **반대다.** 비싼 것은 분석이고 그건 문단에 붙어 있다."""
    with session_scope() as db:
        stored = articles.store(db, draft(), picked_for=date(2026, 11, 1))
        assert stored.article.picked_for == date(2026, 11, 1)

        again = articles.store(db, draft(), picked_for=date(2026, 11, 2))
        assert again.article.picked_for == date(2026, 11, 2)


def test_without_a_picked_day_the_article_stays_a_candidate(cloud):
    """비어 있으면 아직 안 고른 후보다 — `uq_article_day_source` 에 걸리지 않는다."""
    with session_scope() as db:
        stored = articles.store(db, draft())
        assert stored.article.picked_for is None


@pytest.mark.parametrize(
    "body",
    [
        "Ukraine has resumed its attacks on Russian oil refineries in defiance.",
        "<p>Short line.</p><p>Also short.</p>",
        "<aside><p>Related: an earlier report on the refinery strikes in October</p></aside>",
    ],
    ids=["태그가-없다", "전부-50자-미만", "본문이-추천-블록뿐"],
)
def test_a_body_that_does_not_split_is_refused(cloud, body):
    """**문단 0개를 앉히면 미리 분석이 영원히 "다 됐다" 로 읽힌다.**"""
    with session_scope() as db:
        with pytest.raises(ArticleBodyError):
            articles.store(db, draft(body=body))

        assert db.query(Article).count() == 0
