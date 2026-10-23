"""골라 온 기사를 문단마다 미리 분석해 둔다 (M13-T5).

규약은 `app/services/prepare.py` 머리말. 여기서 지키는 것은 넷이다.

- **온전한 것은 다시 돌리지 않는다** — 72 호출이 공짜가 아니다
- **일부 실패는 재시도 대상이고, 재시도는 덮어쓴다** — 행이 둘이 되면 제약에 걸린다
- **전부 실패하면 멈춘다** — 키가 죽었는데 남은 문단을 더 때리지 않는다
- **운영자 키가 없으면 시작하지 않는다** — 빈 키로 72번 헛돌지 않는다
"""

import json

import pytest

from app.auth.crypto import KeyCipher
from app.config import get_settings
from app.db import Article, ArticleParagraph, ParagraphAnalysis, User, session_scope
from app.errors import OperatorKeyRequiredError
from app.services import operator, prepare
from app.services.analyzer import AnalyzerService
from tests.fake_provider import PART_PAYLOADS, FakeProvider
from tests.helpers_prepare import PARAGRAPHS, make_article, operator_with_key

# ------------------------------------------------- 운영자 키가 없으면 시작하지 않는다


def test_without_an_operator_there_is_nothing_to_borrow_a_key_from(cloud):
    """회원이 있어도 플래그가 없으면 만들 수 없다. **조용히 아무 키나 집지 않는다.**"""
    with session_scope() as db:
        db.add(User(google_sub="s1", email="a@b.c"))
        db.commit()

        with pytest.raises(OperatorKeyRequiredError, match="운영자 계정이 없습니다"):
            prepare.analyzer_for(db, _cipher(), get_settings())


def test_an_operator_without_a_key_stops_before_the_first_call(cloud):
    """**빈 키로 시작하면 문단마다 한 번씩 실패하며 72번을 헛돈다.**"""
    with session_scope() as db:
        db.add(User(google_sub="op", email=operator.OPERATOR_EMAIL, is_operator=True))
        db.commit()

        with pytest.raises(OperatorKeyRequiredError, match="키가 등록되지 않았습니다"):
            prepare.analyzer_for(db, _cipher(), get_settings())


def test_the_operators_key_builds_the_fixed_provider(cloud):
    """**운영자의 활성 선택을 따르지 않는다** — 바꾸면 모든 회원의 글감이 흔들린다."""
    with session_scope() as db:
        owner = operator_with_key(db, _cipher(), active_provider="openai")
        assert owner.active_provider == "openai"

        analyzer = prepare.analyzer_for(db, _cipher(), get_settings())

    assert analyzer.provider.model == "gemini-3.5-flash-lite"
    assert type(analyzer.provider).__name__ == "GeminiProvider"


# ----------------------------------------------------------------- 채운다


async def test_every_paragraph_gets_an_analysis(cloud, monkeypatch):
    with session_scope() as db:
        article = make_article(db, _cipher())
        report = await _run(db, article, monkeypatch)

        rows = _rows(db, article.id)

    assert report.prepared == len(PARAGRAPHS)
    assert report.skipped == 0
    assert report.stopped_at is None
    assert [r.level for r in rows] == [prepare.JOB_LEVEL] * len(PARAGRAPHS)


async def test_the_stored_shape_matches_the_members_own_records(cloud, monkeypatch):
    """같은 분석기가 만들고 **같은 화면이 읽는다.** 모양이 갈리면 화면이 둘이 된다."""
    with session_scope() as db:
        article = make_article(db, _cipher())
        await _run(db, article, monkeypatch)

        row = _rows(db, article.id)[0]

    assert row.result["translation"]
    assert row.result["schema_version"] >= 1, "records.stamp 를 안 찍었다"
    assert row.markdown["full"].startswith("### 자연스러운 번역")
    assert row.failed_parts == []
    assert row.model == "fake-model"


async def test_running_again_does_not_spend_calls_on_what_is_done(cloud, monkeypatch):
    """**몇 번 불러도 안전하다.** 그것이 재시도 수단이다."""
    with session_scope() as db:
        article = make_article(db, _cipher())
        await _run(db, article, monkeypatch)

        provider = FakeProvider()
        again = await _run(db, article, monkeypatch, provider=provider)

    assert again.skipped == len(PARAGRAPHS)
    assert again.touched == 0
    assert provider.calls == [], "온전한 문단에 또 호출을 보냈다"


# ------------------------------------------------- 일부 실패는 재시도 대상이다


async def test_a_half_failed_paragraph_is_kept_but_marked(cloud, monkeypatch):
    """살아난 파트는 보여줄 수 있으니 **행은 남긴다.** 다만 재시도 대상으로 남는다."""
    with session_scope() as db:
        article = make_article(db, _cipher())

        report = await _run(db, article, monkeypatch, provider=FakeProvider({"overview": "{}"}))
        rows = _rows(db, article.id)

    assert report.prepared == len(PARAGRAPHS)
    assert report.partial == len(PARAGRAPHS)
    assert all(r.failed_parts == ["overview"] for r in rows)
    assert all(r.result["translation"] for r in rows), "살아난 파트가 버려졌다"


async def test_the_retry_overwrites_the_row_instead_of_adding_one(cloud, monkeypatch):
    """`(paragraph_id, level)` 이 유일하다 — 새로 넣으면 제약에 걸린다."""
    with session_scope() as db:
        article = make_article(db, _cipher())
        await _run(db, article, monkeypatch, provider=FakeProvider({"overview": "{}"}))
        before = [r.id for r in _rows(db, article.id)]

        report = await _run(db, article, monkeypatch)
        after = _rows(db, article.id)

    assert report.retried == len(PARAGRAPHS)
    assert report.prepared == 0
    assert report.partial == 0
    assert [r.id for r in after] == before, "행을 새로 만들었다"
    assert all(r.failed_parts == [] for r in after)
    assert all(r.result["overview"] for r in after), "덮어쓰지 않았다"


# --------------------------------------------- 전부 실패하면 그 자리에서 멈춘다


async def test_a_dead_provider_stops_the_run_instead_of_burning_the_rest(cloud, monkeypatch):
    """문단 탓이 아니다. 키가 한도에 걸렸거나 제공자가 죽은 것이다."""
    broken = FakeProvider({field: "not json" for field in _PART_FIELDS})

    with session_scope() as db:
        article = make_article(db, _cipher())
        report = await _run(db, article, monkeypatch, provider=broken)

        rows = _rows(db, article.id)

    assert report.stopped_at == 1, "첫 문단에서 멈춰야 한다"
    assert report.touched == 0
    assert rows == [], "전부 실패한 문단의 행을 남겼다"


async def test_what_was_done_before_the_provider_died_survives(cloud, monkeypatch):
    """**문단마다 커밋한다.** 끝에 한 번 커밋하면 중간에 죽을 때 그때까지 쓴 호출이
    전부 버려진다.

    그래서 멈춘 뒤 **되돌려 본다.** 죽은 프로세스는 끝 커밋을 못 한다 —
    `session_scope` 가 빠져나갈 때 대신 커밋해 주므로, 그걸 믿으면 커밋을 지워도
    검사가 통과한다. **실제로 지워 보고 확인했다.**
    """
    with session_scope() as db:
        article = make_article(db, _cipher())
        # 첫 문단은 네 파트 다 정상, 둘째 문단부터 **네 파트가 전부** 깨진다.
        # 파트 하나만 깨면 `analyze` 는 부분 실패로 끝나고 멈추지 않는다 — 그건 위의
        # `test_a_half_failed_paragraph_is_kept_but_marked` 가 보는 경우다.
        provider = FakeProvider(
            {
                field: [json.dumps(PART_PAYLOADS[field], ensure_ascii=False), "not json"]
                for field in _PART_FIELDS
            }
        )

        report = await _run(db, article, monkeypatch, provider=provider)

        # 끝 커밋이 없었던 셈으로 되돌린다. 문단마다 커밋했으면 첫 문단은 남는다.
        db.rollback()
        rows = _rows(db, article.id)

    assert report.prepared == 1
    assert report.stopped_at == 2
    assert len(rows) == 1, "첫 문단의 결과가 사라졌다"


# ----------------------------------------------------------------- 거들기

_PART_FIELDS = ("translation", "expressions", "structures", "overview")


def _cipher() -> KeyCipher:
    return KeyCipher(get_settings().encryption_key)


async def _run(db, article, monkeypatch, *, provider: FakeProvider | None = None):
    """`analyzer_for` 만 가짜로 바꿔 끼운다 — 나머지 경로는 그대로 돈다."""
    service = AnalyzerService(provider or FakeProvider())
    monkeypatch.setattr(prepare, "analyzer_for", lambda *a, **k: service)
    return await prepare.article(db, article, _cipher(), get_settings())


def _rows(db, article_id: int) -> list[ParagraphAnalysis]:
    return (
        db.query(ParagraphAnalysis)
        .join(ArticleParagraph)
        .filter(ArticleParagraph.article_id == article_id)
        .order_by(ArticleParagraph.ordinal)
        .all()
    )


def test_the_helpers_build_what_the_tests_assume(cloud):
    """**먼저 이것부터.** 문단이 안 만들어지면 위 검사들이 빈 목록을 훑으며 통과한다."""
    with session_scope() as db:
        article = make_article(db, _cipher())

        assert db.query(Article).count() == 1
        assert len(prepare._paragraphs(db, article.id)) == len(PARAGRAPHS) >= 2
        assert operator.find(db) is not None
