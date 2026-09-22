"""분석 기록을 Postgres 에 남긴다.

전에는 브라우저 localStorage 에 두었는데, 원문 텍스트를 중복 판정 기준으로 써서
같은 문장을 난이도만 바꿔 다시 분석하면 이전 결과가 덮였다.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import AnalysisRecord, session_scope
from app.deps import get_provider
from app.main import create_app
from tests.fake_provider import FakeProvider


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as c:
        yield c


def analyze(client, text, level="intermediate"):
    resp = client.post("/api/analyze", json={"text": text, "level": level})
    assert resp.status_code == 200
    return resp


def test_analysis_is_saved(client):
    analyze(client, "across the pond and back again")

    rows = client.get("/api/history").json()

    assert len(rows) == 1
    assert rows[0]["source_text"] == "across the pond and back again"
    assert rows[0]["level"] == "intermediate"


def test_same_text_at_different_levels_accumulates(client):
    """localStorage 시절에는 같은 원문이면 이전 기록이 덮였다.

    난이도를 바꿔 가며 같은 문단을 비교하는 것이 이 도구의 쓰임이라, 따로 쌓여야 한다.
    """
    text = "The committee has yet to weigh in on the merger."
    for level in ("beginner", "intermediate", "advanced"):
        analyze(client, text, level)

    rows = client.get("/api/history").json()

    assert len(rows) == 3
    assert [r["level"] for r in rows] == ["advanced", "intermediate", "beginner"]


def test_detail_returns_the_full_result(client):
    analyze(client, "across the pond and back again")
    record_id = client.get("/api/history").json()[0]["id"]

    detail = client.get(f"/api/history/{record_id}").json()

    assert detail["result"]["overview"]["domain"] == "경제·금융 시사 논평"
    assert detail["markdown"]["full"].startswith("### 자연스러운 번역")


def test_saved_records_carry_a_schema_version(client):
    """버전을 남겨 두면 다음 스키마 변경 때 모양을 추측하지 않아도 된다."""
    from app.services.records import RESULT_VERSION

    analyze(client, "across the pond and back again")

    with session_scope() as db:
        assert db.query(AnalysisRecord).one().result["schema_version"] == RESULT_VERSION


def test_old_format_records_still_open(client):
    """구문 해설이 한 칸이던 시절의 기록을 열면 500 이 났다."""
    empty_md = {"translation": "", "expressions": "", "structures": "", "overview": "", "full": ""}
    with session_scope() as db:
        row = AnalysisRecord(
            user_id=1,
            source_text="Had she known what awaited her.",
            level="intermediate",
            result={
                "source_text": "Had she known what awaited her.",
                "translation": "번역",
                "expressions": [],
                "structures": [{"fragment": "Had she known", "explanation": "도치 가정법이다."}],
                "overview": {
                    "frequency": "자주",
                    "formality": "격식",
                    "style": "문어체",
                    "domain": "소설",
                    "comment": "코멘트",
                },
            },
            markdown=empty_md,
            failed_parts=[],
        )
        db.add(row)
        db.flush()
        record_id = row.id

    detail = client.get(f"/api/history/{record_id}")

    assert detail.status_code == 200
    assert detail.json()["result"]["structures"][0]["role"] == "도치 가정법이다."
    assert detail.json()["result"]["overview"]["tone"] == ""


def test_delete_removes_the_record(client):
    analyze(client, "across the pond and back again")
    record_id = client.get("/api/history").json()[0]["id"]

    assert client.delete(f"/api/history/{record_id}").status_code == 200
    assert client.get("/api/history").json() == []


def test_missing_record_is_reported(client):
    assert client.get("/api/history/9999").status_code == 400
