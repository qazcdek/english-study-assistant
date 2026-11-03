"""뉴스를 회원에게 내주는 길 (M13-T6).

규약은 `app/services/articles.py` 와 `app/routers/articles.py` 의 머리말.
여기서 지키는 것은 다섯이다.

- **가장 최근에 고른 한 편**을 준다 — "오늘" 을 이 쪽이 따지지 않는다
- **안 고른 후보는 안 보인다** — 목록에도, id 를 맞혀도
- **뉴스가 없는 것은 오류가 아니다** — 404 가 아니라 `article: null`
- **저장된 모양이 화면이 읽는 모양과 같다** — 미리 분석을 실제 경로로 돌려 본다
- **키가 없어도 읽힌다** — LLM 을 부르지 않으므로 (H-041)
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.auth.crypto import KeyCipher
from app.config import get_settings
from app.db import ArticleParagraph, ParagraphAnalysis, User, session_scope
from app.main import create_app
from tests.fake_provider import FakeProvider
from tests.helpers_prepare import PARAGRAPHS, make_article, run_prepare
from tests.modes import login, make_cloud_user

CURRENT = "/api/articles/current"


# ------------------------------------------------------------- 어느 한 편을 주나


def test_the_most_recently_picked_article_is_the_one_shown(client):
    """**"오늘" 을 화면 쪽이 따지지 않는다.** 09 §3.8 이 오늘 것이 없으면 어제 것을
    보여주라고 규정하므로, 꺼내는 규칙은 "가장 늦게 고른 것" 하나다.
    """
    with session_scope() as db:
        make_article(db, _cipher(), source_id="old", picked_for=date(2026, 10, 30))
        make_article(db, _cipher(), source_id="new", picked_for=date(2026, 10, 31))

    body = client.get(CURRENT).json()

    assert body["article"]["picked_for"] == "2026-10-31"
    assert body["article"]["url"].endswith("new")


def test_a_candidate_that_was_never_picked_is_not_shown(client):
    """`M13-T4` 는 후보를 여러 편 앉히고 **하나만** 고른다. 나머지는 뉴스가 아니다."""
    with session_scope() as db:
        make_article(db, _cipher(), source_id="candidate")

    assert client.get(CURRENT).json()["article"] is None


def test_no_article_is_not_an_error(client):
    """첫 배포 직후와 고르기가 실패하는 동안의 **정상 상태**다."""
    response = client.get(CURRENT)

    assert response.status_code == 200, "빈 상태를 오류로 답했다"
    assert response.json() == {"article": None}


def test_the_date_is_handed_over_as_written(client):
    """`picked_for` 를 서버가 고쳐 주지 않는다.

    **"오늘" 이 어느 시간대인가는 `M13-T4` 의 결정이다** (ONGOING). 화면 쪽이
    여기서 보정하면 그 결정을 선점하고, 두 곳이 각자 시간대를 정하게 된다.
    """
    with session_scope() as db:
        make_article(db, _cipher(), picked_for=date(2026, 11, 1))

    assert client.get(CURRENT).json()["article"]["picked_for"] == "2026-11-01"


# --------------------------------------------------------------- 문단과 분석 유무


def test_paragraphs_come_in_order_without_their_analyses(client):
    """첫 응답은 **본문만**이다. 한 편을 통째로 보내면 128KB 다 (ONGOING 실측)."""
    with session_scope() as db:
        make_article(db, _cipher(), picked_for=date(2026, 11, 1))

    article = client.get(CURRENT).json()["article"]

    assert [p["ordinal"] for p in article["paragraphs"]] == [1, 2, 3]
    assert [p["text"] for p in article["paragraphs"]] == list(PARAGRAPHS)
    assert all("result" not in p and "markdown" not in p for p in article["paragraphs"])


async def test_which_paragraphs_are_prepared_is_reported(client, monkeypatch):
    """미리 분석이 중간에 멈출 수 있다 — 그러면 뒤쪽 문단은 **아직 없다.**

    화면은 이 값을 보고 "준비되지 않았습니다" 를 그린다. 이것이 없으면 펼쳐
    보고서야 404 로 알게 된다.
    """
    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=date(2026, 11, 1))
        await run_prepare(db, article, monkeypatch)

    with session_scope() as db:
        # **마지막 문단의 분석만** 지운다 — 분석 도중에 멈춘 상태를 그대로 만든다.
        last = (
            db.query(ParagraphAnalysis)
            .join(ArticleParagraph, ParagraphAnalysis.paragraph_id == ArticleParagraph.id)
            .filter(ArticleParagraph.ordinal == len(PARAGRAPHS))
            .one()
        )
        db.delete(last)
        db.commit()

    paragraphs = client.get(CURRENT).json()["article"]["paragraphs"]

    assert [p["prepared"] for p in paragraphs] == [True, True, False]


def test_an_article_with_no_analysis_at_all_still_shows_its_body(client):
    """읽을 것은 있다. **분석만 없다.** 빈 화면을 보여줄 이유가 없다."""
    with session_scope() as db:
        make_article(db, _cipher(), picked_for=date(2026, 11, 1))

    article = client.get(CURRENT).json()["article"]

    assert len(article["paragraphs"]) == len(PARAGRAPHS)
    assert all(p["prepared"] is False for p in article["paragraphs"])


def test_the_response_carries_no_level_at_all(client):
    """**분석에서 난이도를 걷어냈다** (`M16`). "어느 난이도로 준비됐나" 가 사라졌으므로
    화면이 그걸 적을 일도 없다 — 칸이 남아 있으면 되살아난다."""
    with session_scope() as db:
        make_article(db, _cipher(), picked_for=date(2026, 11, 1))

    article = client.get(CURRENT).json()["article"]
    assert "level" not in article


# ------------------------------------------------------------- 문단 하나의 분석


async def test_the_stored_analysis_is_handed_over_in_the_shape_the_screen_reads(
    client, monkeypatch
):
    """**`HistoryDetail` 과 같은 칸을 든다** — 같은 화면이 읽기 때문이다.

    미리 분석을 **실제 경로로** 돌린다(가짜인 것은 LLM 하나). 그래서 `prepare` 가
    저장하는 모양이 이 응답 모델과 갈라지면 여기서 깨진다.
    """
    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=date(2026, 11, 1))
        await run_prepare(db, article, monkeypatch)
        article_id = article.id

    body = client.get(f"/api/articles/{article_id}/paragraphs/1").json()

    assert body["ordinal"] == 1
    assert "level" not in body
    assert body["result"]["source_text"] == PARAGRAPHS[0]
    assert body["result"]["translation"]
    assert body["result"]["expressions"], "표현 표가 비었다"
    assert body["result"]["structures"]
    assert body["result"]["overview"]["domain"]
    # `schema_version` 은 응답 모델(`AnalysisResult`)에 칸이 없어 떼어진다 —
    # 회원 기록(`HistoryDetail`)도 같다. 저장 쪽 도장은 `test_prepare.py` 가 본다.
    assert "schema_version" not in body["result"]
    assert body["markdown"]["full"].startswith("### 자연스러운 번역")
    assert body["failed_parts"] == []
    assert body["model"] == "fake-model"


async def test_an_analysis_stored_in_an_older_shape_is_upgraded_on_the_way_out(
    client, monkeypatch
):
    """14 §3.5 는 **공용 표에도 그대로 적용된다.**

    프롬프트를 손보면 결과 모양이 바뀌는데, 이미 저장된 뉴스 분석은 그때 모양으로
    남아 있다. 올리지 않으면 응답 모델이 거부해 **그날 뉴스가 통째로 500** 이 된다
    (회원 기록에서 한 번 겪었다 — `H-002`).
    """
    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=date(2026, 11, 1))
        await run_prepare(db, article, monkeypatch)
        article_id = article.id

    with session_scope() as db:
        row = db.query(ParagraphAnalysis).join(ArticleParagraph).filter(
            ArticleParagraph.ordinal == 1
        ).one()
        # 구문 해설이 `explanation` 한 칸이던 시절의 모양으로 되돌린다.
        stale = dict(row.result)
        stale.pop("schema_version", None)
        stale["structures"] = [{"fragment": "It's unlikely", "explanation": "형식주어 구문이다."}]
        row.result = stale
        db.commit()

    body = client.get(f"/api/articles/{article_id}/paragraphs/1")

    assert body.status_code == 200, "낡은 모양을 올리지 못하고 터졌다"
    structure = body.json()["result"]["structures"][0]
    assert structure["role"] == "형식주어 구문이다.", "옛 explanation 을 옮기지 않았다"
    assert structure["name"] == ""


async def test_a_half_failed_analysis_is_still_handed_over(client, monkeypatch):
    """`M13-T4` 가 갈라 둔 기준이다 — **보여주기는 행이 있으면** 된다.

    한 파트가 고집스럽게 실패하면 그날 뉴스가 아예 안 나오는 쪽이 더 나쁘다.
    화면은 `failed_parts` 를 받아 빈 자리를 표시한다.
    """
    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=date(2026, 11, 1))
        await run_prepare(db, article, monkeypatch, provider=FakeProvider({"overview": "{}"}))
        article_id = article.id

    body = client.get(f"/api/articles/{article_id}/paragraphs/1").json()

    assert body["failed_parts"] == ["overview"]
    assert body["result"]["translation"], "살아난 파트가 버려졌다"


async def test_a_paragraph_of_an_unpicked_article_cannot_be_opened_by_id(client, monkeypatch):
    """**후보의 전문이 번호를 맞혀 열리면 안 된다.**

    출처 약관을 어디까지 받아들일지가 아직 안 끝났다 (`M13-T7`). 고르지 않은
    기사를 내줄 이유가 없다.
    """
    with session_scope() as db:
        article = make_article(db, _cipher(), source_id="candidate")
        await run_prepare(db, article, monkeypatch)
        article_id = article.id

    assert client.get(f"/api/articles/{article_id}/paragraphs/1").status_code == 404


@pytest.mark.parametrize("ordinal", [0, 4, 99])
def test_a_paragraph_that_is_not_there_answers_404(client, ordinal):
    """없는 번호와 아직 분석되지 않은 번호를 **같은 404 로** 답한다 (라우터 머리말)."""
    with session_scope() as db:
        article = make_article(db, _cipher(), picked_for=date(2026, 11, 1))
        article_id = article.id

    assert client.get(f"/api/articles/{article_id}/paragraphs/{ordinal}").status_code == 404


async def test_another_articles_paragraph_is_not_reachable_through_this_one(client, monkeypatch):
    """`ordinal` 은 기사 안에서만 유일하다. `article_id` 를 질의에 끼우지 않으면
    **다른 기사의 같은 번호 문단**이 걸린다.
    """
    with session_scope() as db:
        shown = make_article(db, _cipher(), source_id="shown", picked_for=date(2026, 11, 1))
        shown_id = shown.id
        other = make_article(db, _cipher(), source_id="other", picked_for=date(2026, 10, 1))
        await run_prepare(db, other, monkeypatch)

    # 분석은 `other` 쪽에만 있다. `shown` 으로 물으면 없다고 해야 한다.
    assert client.get(f"/api/articles/{shown_id}/paragraphs/1").status_code == 404


# ------------------------------------------------------------- 누가 읽을 수 있나


def test_reading_the_daily_article_needs_no_api_key(cloud):
    """**LLM 을 부르지 않는다.** 이미 분석된 것을 읽는 것뿐이다.

    키 관문에 묶으면 `H-041` 이 다시 난다 — 키가 없는 회원에게서 읽기까지 숨긴다.
    동의도 묻지 않는다 (기록·나의 표현과 같은 자리).
    """
    with session_scope() as db:
        make_article(db, _cipher(), picked_for=date(2026, 11, 1))
    login(cloud, make_cloud_user(consented=False, with_key=False))

    response = cloud.get(CURRENT)

    assert response.status_code == 200
    assert response.json()["article"] is not None


def test_reading_the_daily_article_needs_a_login_in_cloud(cloud):
    """공용이라고 아무나 보는 것은 아니다. **비로그인 공개는 `M13-T7` 의 판단**이고
    출처 약관에 걸려 있다.
    """
    with session_scope() as db:
        make_article(db, _cipher(), picked_for=date(2026, 11, 1))

    assert cloud.get(CURRENT).status_code == 401


def test_local_has_the_route_but_nothing_in_it(both_modes):
    """**모드 분기를 두지 않은 결과를 확인한다** (09 §3.8).

    local 에도 경로가 있고 404 가 아니다. 다만 공용 뉴스를 local 에서는 아무도
    채우지 않으므로 늘 비어 있다 — 분기 하나를 빼먹어도 local 에서 안 도는 것이
    그 절이 고른 장치다. 탭을 감추는 것은 화면 쪽이 한다.
    """
    response = both_modes.client.get(CURRENT)

    assert response.status_code == 200, "두 모드 모두 경로가 있어야 한다"
    assert response.json()["article"] is None


# ----------------------------------------------------------------- 거들기


@pytest.fixture
def client(cloud):
    """로그인까지 끝난 cloud 회원. 대부분의 검사가 읽기만 한다."""
    login(cloud, make_cloud_user())
    return cloud


def _cipher() -> KeyCipher:
    return KeyCipher(get_settings().encryption_key)


def test_the_helpers_build_what_the_tests_assume(client):
    """**먼저 이것부터.** 기사가 안 세워지면 위 검사들이 빈 응답을 보고 통과한다."""
    with session_scope() as db:
        picked = make_article(db, _cipher(), source_id="picked", picked_for=date(2026, 11, 1))
        candidate = make_article(db, _cipher(), source_id="candidate")

        assert picked.picked_for is not None
        assert candidate.picked_for is None
        assert len(PARAGRAPHS) >= 3

    assert client.get(CURRENT).json()["article"] is not None


# ------------------------------------- 운영자만 지난 뉴스를 본다 (M13-T13)

PICKED = "/api/articles/picked"


def test_a_member_cannot_see_the_list_at_all(client):
    """**회원 화면은 "하루 한 편" 이 전제다** (01 · 09 §3.8). 403 이지 404 가 아니다 —
    404 로 두면 경로가 썩었는지 자격이 없는지 운영자 자신도 구별하지 못한다."""
    response = client.get(PICKED)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_the_operator_sees_every_picked_article_newest_first(cloud):
    """하루 한 편이 쌓인다. **최신순이어야** 어제 것을 바로 찾는다."""

    with session_scope() as db:
        for day in (date(2026, 11, 1), date(2026, 11, 3), date(2026, 11, 2)):
            make_article(
                db, _cipher(), source_id=f"world/{day.isoformat()}", picked_for=day
            )
        # 안 고른 후보도 하나 세운다 — 목록에 끼면 안 된다.
        make_article(db, _cipher(), source_id="world/candidate", picked_for=None)

    with TestClient(create_app()) as fresh:
        me = make_cloud_user()
        with session_scope() as db:
            db.get(User, me).is_operator = True
            db.commit()
        login(fresh, me)

        body = fresh.get(PICKED).json()

    assert [a["picked_for"] for a in body["articles"]] == [
        "2026-11-03",
        "2026-11-02",
        "2026-11-01",
    ], "최신순이 아니다"
    assert all(a["paragraphs"] for a in body["articles"]), "문단 본문이 비었다"


def test_the_list_carries_the_same_shape_as_the_single_article(cloud):
    """**목록용으로 줄인 모양을 따로 두지 않는다** — 화면이 두 가지를 그리게 된다."""

    with session_scope() as db:
        make_article(db, _cipher(), picked_for=date(2026, 11, 1))

    with TestClient(create_app()) as fresh:
        me = make_cloud_user()
        with session_scope() as db:
            db.get(User, me).is_operator = True
            db.commit()
        login(fresh, me)

        one = fresh.get(CURRENT).json()["article"]
        listed = fresh.get(PICKED).json()["articles"][0]

    assert set(one) == set(listed)
    assert one == listed


def test_the_account_tells_the_screen_whether_to_offer_the_list(cloud):
    """**권한은 서버가 본다.** 이 값은 보여줄지 말지에만 쓴다 — 고쳐도 목록은 안 열린다."""

    with TestClient(create_app()) as fresh:
        me = make_cloud_user()
        login(fresh, me)
        assert fresh.get("/api/auth/me").json()["is_operator"] is False

        with session_scope() as db:
            db.get(User, me).is_operator = True
            db.commit()

        assert fresh.get("/api/auth/me").json()["is_operator"] is True
