"""골라 온 기사를 공용 표에 앉힌다 (M13-T8).

규약은 `app/services/articles.py` 머리말. 여기서 지키는 것은 셋이다.

- **몇 번 넣어도 같다** — 기사 행도 문단도 두 벌이 되지 않는다
- **이미 있는 문단은 고치지 않는다** — 문단 id 에 분석이 붙어 있다
- **쪼개지지 않는 본문은 거부한다** — 문단 0개는 "다 됐다" 로 읽힌다

쪼개기 규칙 자체는 `test_paragraphs.py` 가 든다. 여기서는 **그 규칙을 타는지**만 본다.
"""

from datetime import UTC, date, datetime

import pytest

from app.db import Article, ArticleParagraph, ParagraphAnalysis, session_scope
from app.errors import ArticleBodyError, ArticleCreditError, ArticleLengthError
from app.services import articles
from app.services.paragraphs import WORD_LIMIT

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
        "byline": "Luke Harding in Kyiv",
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


# -------------------------------------- 약관 상한은 앉힐 때 걸린다 (M13-T9)


def long_body(counts: list[int]) -> str:
    """낱말 수를 지정한 문단들로 본문 HTML 을 만든다.

    낱말을 `w1 w2 …` 로 **다르게** 둔다 — 같은 낱말을 반복하면 어느 문단이
    남았는지 본문으로 구별할 수 없다.
    """
    out = []
    for index, count in enumerate(counts, start=1):
        out.append("<p>" + " ".join(f"p{index}w{n}" for n in range(count)) + "</p>")
    return "".join(out)


def test_the_body_is_cut_to_the_terms_limit_when_it_is_first_stored(cloud):
    """**앉힐 때 자른다.** 넣어 두고 보여줄 때 가리면 전문이 DB 에 남는다."""
    with session_scope() as db:
        stored = articles.store(db, draft(body=long_body([300, 150, 100, 80])))

        # 300+150=450. 셋째를 넣으면 550 이라 둘까지.
        assert stored.paragraphs == 2
        assert stored.skipped == 2

        rows = db.query(ArticleParagraph).order_by(ArticleParagraph.ordinal).all()
        assert [r.ordinal for r in rows] == [1, 2]
        assert sum(len(r.text.split()) for r in rows) == 450
        # 버린 문단의 본문이 **한 글자도 남지 않는다.**
        assert "p3w0" not in " ".join(r.text for r in rows)


def test_an_article_with_no_paragraph_inside_the_limit_is_refused(cloud):
    """**다음 인기 기사로 넘어가야 하는 경우다** — 쪼개기는 성공했다."""
    with session_scope() as db:
        with pytest.raises(ArticleLengthError):
            articles.store(db, draft(body=long_body([600, 700])))

        # 기사 행도 남기지 않는다. 남기면 후보 목록에 쓸 수 없는 것이 낀다.
        assert db.query(Article).count() == 0


def test_the_length_refusal_is_caught_by_the_body_refusal(cloud):
    """고르는 쪽(`M13-T4`)이 `except ArticleBodyError` 하나만 적어도
    **이 경우를 빼먹을 수 없다.** 그래서 물려받게 두었다."""
    with session_scope() as db, pytest.raises(ArticleBodyError):
        articles.store(db, draft(body=long_body([600, 700])))


def test_a_paragraph_already_stored_beyond_the_limit_is_deleted(cloud):
    """상한이 생기기 전에 앉힌 기사가 **약관을 넘긴 채 남는 것은 선택지가 아니다.**

    개발 DB 의 기사 #1 이 바로 이 상태였다 — 16문단 688단어.
    """
    with session_scope() as db:
        articles.store(db, draft(body=long_body([300, 150])))
        # 상한이 없던 때처럼 꼬리를 손으로 밀어 넣는다.
        article_id = db.query(Article).one().id
        for ordinal in (3, 4):
            db.add(
                ArticleParagraph(
                    article_id=article_id,
                    ordinal=ordinal,
                    text=" ".join(f"tail{ordinal}w{n}" for n in range(100)),
                )
            )
        db.commit()
        assert db.query(ArticleParagraph).count() == 4

        again = articles.store(db, draft(body=long_body([300, 150])))

        assert again.trimmed == 2
        assert again.paragraphs == 2
        rows = db.query(ArticleParagraph).order_by(ArticleParagraph.ordinal).all()
        assert [r.ordinal for r in rows] == [1, 2]


def test_trimming_takes_the_analyses_of_the_deleted_paragraphs_and_no_others(cloud):
    """`ON DELETE CASCADE` 다. **상한 안쪽 문단의 분석은 그대로 남아야 한다** —
    그게 안 되면 다시 넣을 때마다 수십 번의 호출이 날아간다."""
    with session_scope() as db:
        articles.store(db, draft(body=long_body([300, 150])))
        article_id = db.query(Article).one().id
        db.add(
            ArticleParagraph(
                article_id=article_id,
                ordinal=3,
                text=" ".join(f"tailw{n}" for n in range(100)),
            )
        )
        db.commit()

        rows = db.query(ArticleParagraph).order_by(ArticleParagraph.ordinal).all()
        for row in rows:
            db.add(
                ParagraphAnalysis(
                    paragraph_id=row.id,
                    result={"schema_version": 3},
                    markdown={"full": ""},
                    failed_parts=[],
                    model="fake",
                )
            )
        db.commit()
        kept_ids = {rows[0].id, rows[1].id}

        articles.store(db, draft(body=long_body([300, 150])))

        left = {a.paragraph_id for a in db.query(ParagraphAnalysis).all()}
        assert left == kept_ids


def test_the_paragraph_numbers_are_not_renumbered_after_a_trim(cloud):
    """**번호를 다시 매기면 남은 분석이 다른 문단에 붙은 것처럼 보인다.**
    화면은 문단 번호로 분석을 찾는다 (`M13-T6`)."""
    with session_scope() as db:
        # 첫 문단 하나가 상한을 넘겨 시작점이 2번이 되는 모양을 손으로 만든다.
        articles.store(db, draft(body=long_body([300])))
        article_id = db.query(Article).one().id
        first = db.query(ArticleParagraph).one()
        first.text = " ".join(f"huge{n}" for n in range(WORD_LIMIT + 1))
        db.add(
            ArticleParagraph(
                article_id=article_id,
                ordinal=2,
                text=" ".join(f"ok{n}" for n in range(80)),
            )
        )
        db.commit()

        again = articles.store(db, draft(body=long_body([300])))

        assert again.trimmed == 1
        rows = db.query(ArticleParagraph).all()
        # 1번이 지워졌고 2번은 **2번으로 남는다.**
        assert [r.ordinal for r in rows] == [2]


# ------------------------------------ 기자 크레딧은 약관이 요구한다 (M13-T10)


def test_the_byline_is_stored_as_the_source_gave_it(cloud):
    """**쪼개 담지 않는다.** `Luke Harding in Kyiv` 가 그대로 크레딧이다 —
    이름만 뽑으려 파싱하면 크레딧이 원문과 달라진다."""
    with session_scope() as db:
        stored = articles.store(db, draft(byline="Jon Henley Europe correspondent"))

        assert stored.article.byline == "Jon Henley Europe correspondent"


@pytest.mark.parametrize("byline", ["", "   ", "\n"], ids=["빈-문자열", "공백만", "줄바꿈만"])
def test_an_article_without_a_byline_is_refused(cloud, byline):
    """**약관이 "반드시" 라고 한다.** 빈 크레딧으로 앉히면 화면이 크레딧 없이
    번역을 내보내는 쪽으로 조용히 기운다."""
    with session_scope() as db:
        with pytest.raises(ArticleCreditError):
            articles.store(db, draft(byline=byline))

        assert db.query(Article).count() == 0


def test_the_credit_refusal_is_caught_by_the_body_refusal(cloud):
    """`ArticleLengthError` 와 같은 자리 — 원인은 셋이 달라도 할 일은 하나다."""
    with session_scope() as db, pytest.raises(ArticleBodyError):
        articles.store(db, draft(byline=""))


def test_the_byline_is_overwritten_on_an_article_already_stored(cloud):
    """크레딧 칸이 생기기 전에 앉힌 기사를 채우는 길이 **이것뿐이다.**
    문단과 달리 아무것도 매달려 있지 않다 (`picked_for` 와 같은 사정)."""
    with session_scope() as db:
        articles.store(db, draft(byline="Luke Harding in Kyiv"))
        # 크레딧 칸이 생기기 전의 상태를 손으로 만든다.
        db.query(Article).one().byline = ""
        db.commit()

        again = articles.store(db, draft(byline="Luke Harding"))

        assert again.article.byline == "Luke Harding"


def test_a_byline_with_padding_is_trimmed(cloud):
    """출처가 준 줄에 공백이 붙어 올 수 있다. 화면에 그대로 찍히면 어긋나 보인다."""
    with session_scope() as db:
        stored = articles.store(db, draft(byline="  Kat Wong \n"))

        assert stored.article.byline == "Kat Wong"
