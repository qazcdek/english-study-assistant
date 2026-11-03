"""손으로 글감을 넣는 도구 (M13-T8) — `./dev.sh article`.

표에 앉히는 규약은 `test_articles.py` 가 든다. 여기서 보는 것은 **도구 자신의 셋**이다.

- **자격증명을 찍지 않는다** — 어느 DB 인지 말하면서 비밀값을 흘리면 안 된다
- **환경 파일을 셸 없이 읽고, 이미 있는 값을 덮지 않는다**
- **빠진 칸을 한꺼번에 알려준다** — 하나씩 알려주면 같은 명령을 여섯 번 다시 친다
"""

import json
import os
from datetime import UTC, datetime

import pytest

from tools import article

SECRET = "npg_SuPeRsEcReT123"
PG_URL = f"postgresql+psycopg://neondb_owner:{SECRET}@ep-x-pooler.example.neon.tech/neondb"

GOOD = {
    "source": "guardian",
    "source_id": "world/2026/nov/01/example",
    "url": "https://www.theguardian.com/world/2026/nov/01/example",
    "title": "An example article",
    "section": "world",
    "published_at": "2026-11-01T17:20:18Z",
    "body": "<p>Long enough to pass the fifty character floor in paragraphs.py.</p>",
}


def test_saying_which_database_never_says_the_password():
    """**비밀값은 `@` 앞에 있다.** 사용자·비밀번호·`npg_` 한 조각도 나오지 않는다."""
    shown = article.where(PG_URL)

    assert SECRET not in shown
    assert "neondb_owner" not in shown
    assert "ep-x-pooler.example.neon.tech" in shown


def test_a_url_without_credentials_is_shown_whole():
    """SQLite 처럼 비밀값이 없으면 자를 것이 없다 — 잘라 내면 어느 파일인지 모른다."""
    assert article.where("sqlite+pysqlite:///./local-cloud.db") == (
        "sqlite+pysqlite:///./local-cloud.db"
    )


@pytest.fixture
def env(monkeypatch) -> dict[str, str]:
    """`os.environ` 을 **사본으로 바꿔 끼운다.**

    `load_env` 는 일부러 프로세스 환경을 직접 고치므로, `monkeypatch.setenv` 로는
    되돌릴 수 없다 — 이 검사가 심은 `APP_MODE=cloud` 가 뒤에 도는 다른 검사까지
    따라간다.
    """
    fake: dict[str, str] = {}
    monkeypatch.setattr(os, "environ", fake)
    return fake


def test_the_env_file_is_read_without_a_shell(tmp_path, env):
    """**bash 가 이 파일을 보지 않는다.** 주석과 빈 줄은 건너뛴다."""
    path = tmp_path / ".env.cloud"
    path.write_text("# 주석\n\nAPP_MODE=cloud\nSESSION_SECRET=abc=def\n", encoding="utf-8")

    article.load_env(path)

    assert env["APP_MODE"] == "cloud"
    # `=` 가 값 안에 있어도 자르지 않는다 — Fernet 키와 base64 가 그렇게 끝난다.
    assert env["SESSION_SECRET"] == "abc=def"


def test_the_env_file_does_not_overwrite_what_is_already_set(tmp_path, env):
    """명령줄에서 하나만 바꿔 끼울 수 있어야 한다."""
    path = tmp_path / ".env.cloud"
    path.write_text("APP_MODE=cloud\n", encoding="utf-8")
    env["APP_MODE"] = "local"

    article.load_env(path)

    assert env["APP_MODE"] == "local"


def test_every_missing_field_is_named_at_once(tmp_path):
    """하나씩 알려주면 같은 명령을 여섯 번 다시 친다."""
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"source": "guardian", "body": "<p>x</p>"}), encoding="utf-8")

    with pytest.raises(SystemExit, match="source_id.*url.*title.*section.*published_at"):
        article.read_draft(path)


def test_the_published_time_keeps_its_zone(tmp_path):
    """가디언은 `Z` 로 끝내 준다. 시간대를 잃으면 `published_at` 이 로컬 시각이 된다."""
    path = tmp_path / "a.json"
    path.write_text(json.dumps(GOOD), encoding="utf-8")

    draft = article.read_draft(path)

    assert draft.published_at == datetime(2026, 11, 1, 17, 20, 18, tzinfo=UTC)


# ------------------------------------- 약관 상한이 한 일을 말해 준다 (M13-T9)


def test_nothing_is_said_when_nothing_was_cut():
    """평범한 기사에 군말을 붙이지 않는다."""
    assert article.cut_notes(skipped=0, trimmed=0, limit=500) == []


def test_the_skipped_paragraphs_are_reported_with_the_limit():
    """**조용히 자르면 안 된다.** 몇 단어 상한에 걸렸는지도 함께 말한다."""
    notes = article.cut_notes(skipped=5, trimmed=0, limit=500)

    assert len(notes) == 1
    assert "500단어" in notes[0]
    assert "5문단" in notes[0]


def test_deleting_already_stored_paragraphs_says_the_analyses_went_too():
    """지운 쪽은 **분석까지 사라진다** — 그걸 안 말하면 운영자가 모른다."""
    notes = article.cut_notes(skipped=0, trimmed=2, limit=500)

    assert len(notes) == 1
    assert "2문단" in notes[0]
    assert "분석" in notes[0]


def test_both_can_happen_at_once():
    """본문은 잘리고, 전에 넣어 둔 꼬리도 지워지는 경우다."""
    assert len(article.cut_notes(skipped=5, trimmed=2, limit=500)) == 2
