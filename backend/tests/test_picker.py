"""하루 한 편을 고르고 미리 분석한다 (M13-T4).

규약은 `app/services/daily.py` 와 `app/services/guardian.py` 머리말.
여기서 지키는 것은 여섯이다.

- **"오늘" 은 한국 날짜다** — UTC 로 세면 뉴스가 매일 오전 9시에 바뀐다
- **운영자가 없으면 가디언을 치지도 않는다** — local 에서 이 기능을 끄는 장치
- **부분 실패는 "안 된 것"** — 세 파트만 성공한 행이 "됐음" 으로 읽히면 안 된다
- **쿨다운은 시간으로 풀린다** — 하루 시도 상한이 아니다
- **관문은 `store()` 하나다** — 분량·크레딧·쪼개기를 여기서 다시 보지 않는다
- **이미 쓴 기사를 다시 고르지 않는다** — 어제 1위가 오늘도 1위다

입력은 **실제 가디언 응답 모양**을 쓴다. 직접 지어낸 `{"id": ..., "body": ...}`
로는 `mostViewed` 가 `response` 안에 있다는 것도, `fields` 가 따로 있다는 것도
확인되지 않는다.
"""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from app.config import get_settings
from app.db import (
    Article,
    ArticleParagraph,
    ParagraphAnalysis,
    PickAttempt,
    session_scope,
)
from app.errors import ArticleBodyError, ArticleSourceError
from app.services import articles, daily, guardian
from tests.helpers_prepare import PARAGRAPHS, make_article, operator_with_key

TODAY = date(2026, 11, 4)


def _cipher():
    from app.auth.crypto import KeyCipher

    return KeyCipher(get_settings().encryption_key)


def body(*texts: str) -> str:
    """가디언이 주는 모양의 본문 HTML."""
    return "".join(f"<p>{text}</p>" for text in texts)


def item(**over) -> dict:
    """`mostViewed` 한 줄. 실제 응답의 칸 이름을 그대로 쓴다."""
    base = {
        "id": "world/2026/nov/04/example",
        "type": "article",
        "sectionId": "world",
        "webPublicationDate": "2026-11-04T06:00:00Z",
        "webTitle": "An example article",
        "webUrl": "https://www.theguardian.com/world/2026/nov/04/example",
        "fields": {
            "byline": "Luke Harding in Kyiv",
            "wordcount": "700",
            "body": body(*PARAGRAPHS),
        },
    }
    fields = {**base["fields"], **over.pop("fields", {})}
    return {**base, **over, "fields": fields}


def client_for(payload: dict, status: int = 200) -> httpx.AsyncClient:
    """`mostViewed` 를 그 자리에 담아 돌려주는 가짜 클라이언트."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def settings_with_key():
    from dataclasses import replace as _replace  # noqa: F401  (pydantic 은 copy 를 쓴다)

    return get_settings().model_copy(update={"guardian_api_key": "GUARDIAN-TEST-KEY"})


# --------------------------------------------- "오늘" 은 한국 날짜다


def test_today_is_the_korean_date_not_utc():
    """UTC 로 세면 **뉴스가 매일 오전 9시에 바뀐다.** 읽는 사람은 한국에 있다.

    식을 옮겨 적지 않고 **그 함수를 부른다.** 처음에는 `(now + KST).date()` 를
    검사에 베껴 썼는데, 함수를 UTC 로 되돌려도 검사가 통과했다 — 깨뜨려 보고 알았다.
    """
    # 한국은 이미 11월 4일 오전 8시인데 UTC 는 아직 11월 3일인 시각.
    assert daily.today(datetime(2026, 11, 3, 23, 0, tzinfo=UTC)) == date(2026, 11, 4)
    # 한국 한낮은 그날이다 (UTC 로는 03:00).
    assert daily.today(datetime(2026, 11, 4, 3, 0, tzinfo=UTC)) == date(2026, 11, 4)


def test_the_day_turns_over_at_six_in_the_morning_not_at_midnight():
    """**자정에 바꾸면 밤늦게 읽던 사람이 글을 잃는다** — 23시 50분에 읽던 글이
    10분 뒤에 어제 것이 된다. 6시로 밀면 밤 공부는 같은 글로 끝나고 새벽 공부는
    그 시각부터 새 글을 받는다."""
    # 한국 23:59 — 자정을 안 넘겼다.
    assert daily.today(datetime(2026, 11, 3, 14, 59, tzinfo=UTC)) == date(2026, 11, 3)
    # 한국 00:00 — **자정에는 안 바뀐다.** 밤 공부가 같은 글로 끝난다.
    assert daily.today(datetime(2026, 11, 3, 15, 0, tzinfo=UTC)) == date(2026, 11, 3)
    # 한국 05:59 — 아직 어제다.
    assert daily.today(datetime(2026, 11, 3, 20, 59, tzinfo=UTC)) == date(2026, 11, 3)
    # 한국 06:00 — 여기서 넘어간다.
    assert daily.today(datetime(2026, 11, 3, 21, 0, tzinfo=UTC)) == date(2026, 11, 4)


def test_the_boundary_is_a_separate_decision_from_the_timezone():
    """`KST` 는 **어디에 있나**, `DAY_STARTS_AT` 은 **하루를 어디서 끊나**다.
    한 값에 섞으면 시간대를 고칠 때 경계가 따라 움직인다."""
    assert daily.KST == timedelta(hours=9)
    assert daily.DAY_STARTS_AT == timedelta(hours=6)


def test_an_article_with_zero_paragraphs_never_counts_as_done(cloud):
    """**빈 기사를 "됐음" 으로 읽으면 그날 뉴스가 영영 안 생긴다** — 돌 문단이
    없으므로 분석도 0개이고, `0 < 0` 이 거짓이라 온전해 보인다."""
    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=TODAY)
        db.query(ArticleParagraph).filter(
            ArticleParagraph.article_id == article.id
        ).delete()
        db.commit()

        assert daily.incomplete(db, TODAY) is True


# --------------------------------------------- 관문 넷을 순서대로 본다


def test_without_a_source_key_nothing_runs(cloud):
    """키가 비면 뉴스 고르기만 꺼진다. **앱은 정상으로 뜬다.**

    키를 **일부러 비운 설정**으로 묻는다. 개발 `.env` 에는 가디언 키가 실제로
    들어 있어서 `get_settings()` 를 그대로 쓰면 이 전제가 서지 않는다.
    """
    empty = get_settings().model_copy(update={"guardian_api_key": ""})
    with session_scope() as db:
        operator_with_key(db, _cipher())

        assert daily.should_run(db, empty, day=TODAY) is False


def test_without_an_operator_the_source_is_never_called(cloud):
    """**local 에서 이 기능을 끄는 장치다.** local 의 `.env` 에도 가디언 키가 있지만
    부트스트랩 사용자에게는 운영자 플래그가 없다 (`operator.py`)."""
    with session_scope() as db:
        assert daily.should_run(db, settings_with_key(), day=TODAY) is False


async def test_a_complete_article_for_today_stops_the_run(cloud, monkeypatch):
    """온전한 뉴스가 있으면 **다시 돌리지 않는다.** 44 호출이 공짜가 아니다."""
    from tests.helpers_prepare import run_prepare

    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=TODAY)
        await run_prepare(db, article, monkeypatch)

        assert daily.should_run(db, settings_with_key(), day=TODAY) is False


def test_an_article_with_no_analysis_yet_still_needs_a_run(cloud):
    """기사만 서 있고 분석이 없으면 **아직 안 된 것이다.**"""
    with session_scope() as db:
        make_article(db, _cipher(), picked_for=TODAY)

        assert daily.incomplete(db, TODAY) is True
        assert daily.should_run(db, settings_with_key(), day=TODAY) is True


async def test_a_partly_failed_paragraph_still_needs_a_run(cloud, monkeypatch):
    """**세 파트만 성공한 행을 "됐음" 으로 읽으면** 빈 총평이 모든 회원에게 고정된다."""
    from tests.helpers_prepare import run_prepare

    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=TODAY)
        await run_prepare(db, article, monkeypatch)
        assert daily.incomplete(db, TODAY) is False

        # 한 문단의 한 파트가 실패한 상태로 되돌린다.
        row = (
            db.query(ParagraphAnalysis)
            .join(ArticleParagraph, ParagraphAnalysis.paragraph_id == ArticleParagraph.id)
            .filter(ArticleParagraph.article_id == article.id)
            .first()
        )
        row.failed_parts = ["overview"]
        db.commit()

        assert daily.incomplete(db, TODAY) is True


async def test_yesterdays_complete_article_does_not_count_for_today(cloud, monkeypatch):
    """어제 것은 **빈 화면을 막아 주지만** 오늘 것을 만들 이유를 없애지 않는다."""
    from tests.helpers_prepare import run_prepare

    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=TODAY - timedelta(days=1))
        await run_prepare(db, article, monkeypatch)

        assert daily.incomplete(db, TODAY) is True


# --------------------------------------------- 쿨다운은 시간으로 풀린다


def test_a_fresh_failure_puts_the_run_to_sleep(cloud):
    with session_scope() as db:
        operator_with_key(db, _cipher())
        daily._note(db, TODAY, "테스트")
        db.commit()

        assert daily.resting(db, TODAY) is True
        assert daily.should_run(db, settings_with_key(), day=TODAY) is False


def test_the_cooldown_releases_itself_when_the_time_passes(cloud):
    """**하루 시도 상한이 아니다.** 상한은 다 쓰면 문제가 풀려도 내일까지 뉴스가 없다."""
    with session_scope() as db:
        operator_with_key(db, _cipher())
        daily._note(db, TODAY, "테스트")
        db.commit()
        later = datetime.now(UTC) + daily.COOLDOWN + timedelta(seconds=1)

        assert daily.resting(db, TODAY, now=later) is False


def test_failures_pile_up_on_one_row_per_day_and_source(cloud):
    """`(날짜, 출처)` 마다 한 줄이고 **왜 실패했는지 마지막 이유가 남는다** —
    로그를 뒤지지 않고 알 수 있어야 한다."""
    with session_scope() as db:
        daily._note(db, TODAY, "첫 번째")
        daily._note(db, TODAY, "두 번째")
        db.commit()

        rows = db.query(PickAttempt).all()
        assert len(rows) == 1
        assert rows[0].failures == 2
        assert rows[0].reason == "두 번째"


def test_a_cooldown_for_another_day_does_not_block_today(cloud):
    with session_scope() as db:
        operator_with_key(db, _cipher())
        daily._note(db, TODAY - timedelta(days=1), "어제 실패")
        db.commit()

        assert daily.resting(db, TODAY) is False


# --------------------------------------------- 가져오기


async def test_a_liveblog_is_not_a_candidate():
    """**쪼개기가 아니라 고르기의 일이다** (`paragraphs.py` 가 그렇게 적어 뒀다).
    섞으면 50자 미만 쓰레기가 2% → 11% 로 늘고 "Hm." 이 문단이 된다.
    실측에서 인기 1위가 라이브블로그인 날이 있었다."""
    payload = {
        "response": {
            "mostViewed": [
                item(type="liveblog", id="world/live/2026/nov/04/live"),
                item(),
            ]
        }
    }
    async with client_for(payload) as http:
        drafts = await guardian.candidates(settings_with_key(), client=http)

    assert len(drafts) == 1
    assert "live" not in drafts[0].source_id


async def test_an_empty_popular_list_is_an_error_not_a_quiet_success():
    """조용히 성공으로 두면 **왜 뉴스가 없는지 아무도 모른다.**"""
    async with client_for({"response": {"mostViewed": []}}) as http:
        with pytest.raises(ArticleSourceError):
            await guardian.candidates(settings_with_key(), client=http)


async def test_the_source_key_never_reaches_the_error_message():
    """`httpx` 의 오류 문구에는 요청 URL 이 들어가고 **거기에 api-key 가 붙어 있다.**
    그대로 적으면 쿨다운 표의 `reason` 과 화면에 키가 남는다."""
    async with client_for({"message": "nope"}, status=503) as http:
        with pytest.raises(ArticleSourceError) as caught:
            await guardian.candidates(settings_with_key(), client=http)

    whole = f"{caught.value} {caught.value.detail}"
    assert "GUARDIAN-TEST-KEY" not in whole
    assert "api-key" not in whole


async def test_a_row_missing_what_we_need_is_dropped_not_crashed():
    """출처가 칸을 빼먹을 수 있다. **한 줄 때문에 전체가 실패하면** 그날 뉴스가 없다."""
    payload = {
        "response": {
            "mostViewed": [
                item(webPublicationDate="그런 날짜 없음"),
                {"id": "x", "type": "article"},  # fields 자체가 없다
                item(id="world/2026/nov/04/good"),
            ]
        }
    }
    async with client_for(payload) as http:
        drafts = await guardian.candidates(settings_with_key(), client=http)

    assert [d.source_id for d in drafts] == ["world/2026/nov/04/good"]


async def test_the_popular_order_is_kept_as_given():
    """가디언이 준 순서가 곧 인기 순위다. **다시 매기지 않는다.**"""
    payload = {
        "response": {
            "mostViewed": [item(id=f"world/2026/nov/04/n{n}") for n in (1, 2, 3)]
        }
    }
    async with client_for(payload) as http:
        drafts = await guardian.candidates(settings_with_key(), client=http)

    assert [d.source_id for d in drafts] == [f"world/2026/nov/04/n{n}" for n in (1, 2, 3)]


# --------------------------------------------- 고르기


def draft(**over) -> articles.Draft:
    base = {
        "source": "guardian",
        "source_id": "world/2026/nov/04/example",
        "url": "https://www.theguardian.com/world/2026/nov/04/example",
        "title": "An example article",
        "byline": "Luke Harding in Kyiv",
        "section": "world",
        "published_at": datetime(2026, 11, 4, 6, 0, tzinfo=UTC),
        "body": body(*PARAGRAPHS),
    }
    return articles.Draft(**{**base, **over})


async def test_the_top_candidate_is_used_when_it_passes(cloud):
    with session_scope() as db:
        article_id = await daily._pick(db, [draft(), draft(source_id="second")], TODAY)

        row = db.get(Article, article_id)
        assert row.source_id == "world/2026/nov/04/example"
        assert row.picked_for == TODAY


@pytest.mark.parametrize(
    "broken",
    [
        {"body": "<p>Short.</p>"},
        {"body": body(" ".join(f"w{n}" for n in range(600)))},
        {"byline": ""},
    ],
    ids=["쪼개지지-않는다", "500단어-토막이-없다", "크레딧이-없다"],
)
async def test_a_candidate_that_fails_a_gate_is_skipped_for_the_next(cloud, broken):
    """**관문은 `store()` 하나다.** 셋 다 `ArticleBodyError` 의 자손이므로
    `except ArticleBodyError` 하나로 빼먹을 수 없다 (`M13-T9` · `M13-T10`)."""
    with session_scope() as db:
        article_id = await daily._pick(
            db,
            [draft(source_id="bad", **broken), draft(source_id="good")],
            TODAY,
        )

        assert db.get(Article, article_id).source_id == "good"


async def test_an_article_already_used_as_a_pick_is_skipped(cloud):
    """**어제 1위가 오늘도 1위다.** `store()` 는 `picked_for` 를 덮어쓰므로
    걸러 주지 않으면 같은 글이 또 온다."""
    with session_scope() as db:
        make_article(db, _cipher(), source_id="yesterday", picked_for=TODAY - timedelta(days=1))

        article_id = await daily._pick(
            db, [draft(source_id="yesterday"), draft(source_id="fresh")], TODAY
        )

        assert db.get(Article, article_id).source_id == "fresh"


async def test_a_stored_candidate_that_was_never_picked_can_still_be_used(cloud):
    """`picked_for` 가 빈 행은 **후보**다. 쓴 적이 없으므로 넘기지 않는다."""
    with session_scope() as db:
        make_article(db, _cipher(), source_id="candidate", picked_for=None)

        article_id = await daily._pick(db, [draft(source_id="candidate")], TODAY)

        assert db.get(Article, article_id).source_id == "candidate"


async def test_when_every_candidate_fails_the_picker_says_so(cloud):
    """쿨다운이 적히고 5분 뒤 다시 본다. **조용히 성공으로 두지 않는다.**"""
    with session_scope() as db, pytest.raises(ArticleBodyError):
        await daily._pick(db, [draft(body="<p>Short.</p>")], TODAY)


# --------------------------------------------- 뒤에서 도는 한 바퀴


async def test_a_full_run_stands_up_todays_article_with_its_analyses(cloud, monkeypatch):
    """고르기부터 분석까지 **실제 경로로** 돈다. 가짜인 것은 가디언과 LLM 둘뿐이다."""
    from app.services import prepare
    from app.services.analyzer import AnalyzerService
    from tests.fake_provider import FakeProvider

    with session_scope() as db:
        operator_with_key(db, _cipher())

    async def candidates(*a, **k):
        return [draft()]

    monkeypatch.setattr(guardian, "candidates", candidates)
    service = AnalyzerService(FakeProvider())
    monkeypatch.setattr(prepare, "analyzer_for", lambda *a, **k: service)

    await daily.run(settings_with_key(), day=TODAY)

    with session_scope() as db:
        assert daily.incomplete(db, TODAY) is False
        assert db.query(PickAttempt).count() == 0
        shown = articles.current(db)
        assert shown.article.picked_for == TODAY
        # **문단이 묶였다** (M13-T11) — 세 토막이 120낱말 안이라 한 문단이다.
        assert len(shown.paragraphs) == 1
        assert len(shown.prepared) == len(shown.paragraphs)


async def test_a_failing_source_leaves_a_cooldown_and_throws_nothing(cloud, monkeypatch):
    """**응답 경로가 아니므로 올릴 곳이 없다.** 실패는 표에 적힌다."""
    with session_scope() as db:
        operator_with_key(db, _cipher())

    async def candidates(*a, **k):
        raise ArticleSourceError(detail="연결 실패")

    monkeypatch.setattr(guardian, "candidates", candidates)

    await daily.run(settings_with_key(), day=TODAY)  # 던지지 않는다

    with session_scope() as db:
        row = db.query(PickAttempt).one()
        assert row.failures == 1
        assert "article_source" in row.reason
        assert db.query(Article).count() == 0


async def test_candidates_that_all_fail_the_gates_leave_a_cooldown(cloud, monkeypatch):
    with session_scope() as db:
        operator_with_key(db, _cipher())

    async def candidates(*a, **k):
        return [draft(body="<p>Short.</p>")]

    monkeypatch.setattr(guardian, "candidates", candidates)

    await daily.run(settings_with_key(), day=TODAY)

    with session_scope() as db:
        assert db.query(PickAttempt).one().failures == 1
        assert db.query(Article).count() == 0


async def test_a_run_that_stops_mid_analysis_keeps_what_it_got(cloud, monkeypatch):
    """**재시도는 이어서 돈다.** 처음부터 다시 돌면 재시도 비용이 횟수에 비례한다."""
    from app.services import prepare
    from app.services.analyzer import AnalyzerService
    from tests.fake_provider import FakeProvider

    with session_scope() as db:
        operator_with_key(db, _cipher())

    async def candidates(*a, **k):
        return [draft()]

    monkeypatch.setattr(guardian, "candidates", candidates)
    # 네 파트가 전부 실패하게 두면 첫 문단에서 멈춘다.
    broken = FakeProvider({part: "not json" for part in ("translation", "expressions", "structures", "overview")})
    monkeypatch.setattr(prepare, "analyzer_for", lambda *a, **k: AnalyzerService(broken))

    await daily.run(settings_with_key(), day=TODAY)

    with session_scope() as db:
        # 기사는 섰고, 쿨다운이 적혔고, 다음 요청이 다시 본다.
        assert db.query(Article).count() == 1
        assert db.query(PickAttempt).one().failures == 1
        assert daily.incomplete(db, TODAY) is True


# --------------------------------------------- 방아쇠는 읽는 요청이다


async def test_the_read_request_throws_the_pick_behind_it(cloud, monkeypatch):
    """**요청을 막지 않는다.** 고르기+분석은 수십 초다 — 응답 경로에서 돌리면
    첫 방문자가 그 시간을 전부 기다린다 (`09 §3.8`)."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.routers import articles as router
    from tests.modes import login, make_cloud_user

    thrown: list[tuple] = []
    monkeypatch.setattr(router.daily, "should_run", lambda *a, **k: True)
    monkeypatch.setattr(router.daily, "run", lambda *a, **k: thrown.append(a))

    with TestClient(create_app()) as client:
        login(client, make_cloud_user())
        response = client.get("/api/articles/current")

    assert response.status_code == 200
    assert response.json() == {"article": None}  # 기다리지 않고 바로 답했다
    assert len(thrown) == 1  # 뒤로 던져졌다


def test_a_read_request_throws_nothing_when_there_is_no_reason_to(cloud, monkeypatch):
    """온전한 뉴스가 있는 날 **모든 요청마다 작업을 던지면** 안 된다."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.routers import articles as router
    from tests.modes import login, make_cloud_user

    thrown: list[tuple] = []
    monkeypatch.setattr(router.daily, "should_run", lambda *a, **k: False)
    monkeypatch.setattr(router.daily, "run", lambda *a, **k: thrown.append(a))

    with TestClient(create_app()) as client:
        login(client, make_cloud_user())
        client.get("/api/articles/current")

    assert thrown == []


async def test_a_retry_does_not_go_back_to_the_source(cloud, monkeypatch):
    """**오늘 고른 것이 있으면 다시 고르지 않는다.** 재시도마다 가디언을 치면,
    1위는 이미 쓴 기사라 넘어가고 2위를 앉히려다 `uq_article_day_source` 에 걸린다.
    실제 응답으로 돌려 보고 발견한 자리다."""
    from app.services import prepare
    from app.services.analyzer import AnalyzerService
    from tests.fake_provider import FakeProvider

    with session_scope() as db:
        operator_with_key(db, _cipher())
        make_article(db, _cipher(), source_id="picked/today", picked_for=TODAY)

    called = []

    async def candidates(*a, **k):
        called.append(True)
        return [draft()]

    monkeypatch.setattr(guardian, "candidates", candidates)
    service = AnalyzerService(FakeProvider())
    monkeypatch.setattr(prepare, "analyzer_for", lambda *a, **k: service)

    await daily.run(settings_with_key(), day=TODAY)

    assert called == []  # 출처를 치지 않았다
    with session_scope() as db:
        assert db.query(Article).count() == 1  # 새 기사를 앉히지도 않았다
        assert daily.incomplete(db, TODAY) is False  # 분석은 이어서 채웠다
