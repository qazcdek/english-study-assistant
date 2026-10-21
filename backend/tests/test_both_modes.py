"""두 모드 공통 기능. **local 과 cloud 에서 각각 한 번씩 돈다.**

여기 있는 것들은 모드와 무관하게 똑같이 동작해야 한다. 전에는 이 가운데
상당수가 `test_cloud.py` 안에만 있어서 local 쪽이 깨져도 잡히지 않았다.
실제로 H-002(옛 기록 500)는 두 모드 모두의 버그였는데 따로 고쳤다.
"""

from app.db import AnalysisRecord, session_scope
from app.services.records import RESULT_VERSION

EMPTY_MD = {"translation": "", "expressions": "", "structures": "", "overview": "", "full": ""}


def test_analysis_is_saved_and_readable(both_modes):
    api = both_modes
    assert api.client.post("/api/analyze", json={"text": "across the pond"}).status_code == 200

    history = api.client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["source_text"] == "across the pond"

    detail = api.client.get(f"/api/history/{history[0]['id']}").json()
    assert detail["result"]["overview"]["domain"] == "경제·금융 시사 논평"


def test_usage_is_counted_only_in_cloud(both_modes):
    """회원 각자의 Gemini 한도를 쓰는 cloud 에서만 센다 (09-mode-matrix.md §3.3)."""
    api = both_modes
    api.client.post("/api/analyze", json={"text": "across the pond"})

    assert api.client.get("/api/usage").json()["analyses"] == (1 if api.mode == "cloud" else 0)


def test_new_records_carry_a_schema_version(both_modes):
    """버전을 남겨 두면 다음 스키마 변경 때 모양을 추측하지 않아도 된다."""
    api = both_modes
    api.client.post("/api/analyze", json={"text": "across the pond and back again"})

    with session_scope() as db:
        row = db.query(AnalysisRecord).filter(AnalysisRecord.user_id == api.user_id).one()
        assert row.result["schema_version"] == RESULT_VERSION


def test_old_format_records_still_open(both_modes):
    """프롬프트를 손볼 때마다 결과 스키마가 바뀌었는데, 옛 기록을 열면 500 이 났다."""
    api = both_modes
    with session_scope() as db:
        row = AnalysisRecord(
            user_id=api.user_id,
            source_text="Had she known what awaited her.",
            level="intermediate",
            result={
                "source_text": "Had she known what awaited her.",
                "translation": "번역",
                "expressions": [{"expression": "set foot in", "type": "관용구", "meaning": "발을 들이다"}],
                "structures": [{"fragment": "Had she known", "explanation": "도치 가정법이다."}],
                "overview": {
                    "frequency": "자주",
                    "formality": "격식",
                    "style": "문어체",
                    "domain": "소설",
                    "comment": "코멘트",
                },
            },
            markdown=EMPTY_MD,
            failed_parts=[],
        )
        db.add(row)
        db.flush()
        record_id = row.id

    resp = api.client.get(f"/api/history/{record_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["structures"][0]["role"] == "도치 가정법이다."
    assert body["result"]["overview"]["tone"] == ""
    assert body["result"]["expressions"][0]["nuance"] == ""


def test_vocabulary_add_list_delete(both_modes):
    api = both_modes
    item = {"expression": "sum up", "type": "Phrasal Verb", "meaning": "요약하다"}

    created = api.client.post("/api/vocabulary", json=item).json()
    assert created["expression"] == "sum up"

    # 같은 표현을 다시 담으면 새로 쌓이지 않고 갱신된다.
    api.client.post("/api/vocabulary", json={**item, "meaning": "요약하다, 정리하다"})
    rows = api.client.get("/api/vocabulary").json()
    assert len(rows) == 1
    assert rows[0]["meaning"] == "요약하다, 정리하다"

    assert api.client.delete(f"/api/vocabulary/{rows[0]['id']}").status_code == 200
    assert api.client.get("/api/vocabulary").json() == []


def test_history_entry_can_be_deleted(both_modes):
    api = both_modes
    api.client.post("/api/analyze", json={"text": "across the pond"})
    record_id = api.client.get("/api/history").json()[0]["id"]

    assert api.client.delete(f"/api/history/{record_id}").status_code == 200
    assert api.client.get("/api/history").json() == []
    # 지워진 기록은 400 을 낸다. 404 가 맞지만 지금 동작을 그대로 고정해 둔다 (H-012).
    assert api.client.get(f"/api/history/{record_id}").status_code == 400


def test_my_data_can_be_counted_and_purged(both_modes):
    """모으는 기능만 있고 지우는 수단이 없으면 회원은 자기 데이터를 회수할 수 없다."""
    api = both_modes
    api.client.post("/api/analyze", json={"text": "across the pond"})
    api.client.post("/api/vocabulary", json={"expression": "sum up", "meaning": "요약하다"})

    before = api.client.get("/api/account/data").json()
    assert before["analyses"] == 1 and before["vocabulary"] == 1
    # 사용량 집계는 cloud 에서만 쌓인다 (09-mode-matrix.md §3.3).
    assert before["usage_counters"] == (1 if api.mode == "cloud" else 0)

    deleted = api.client.delete("/api/account/data").json()
    assert deleted == before

    assert api.client.get("/api/history").json() == []
    assert api.client.get("/api/vocabulary").json() == []
    assert api.client.get("/api/account/data").json()["analyses"] == 0


def test_purging_data_keeps_the_account_usable(both_modes):
    """계정은 남아야 한다. 로컬은 사용자 행을 지우면 다음 요청이 깨진다."""
    api = both_modes
    api.client.post("/api/analyze", json={"text": "across the pond"})
    api.client.delete("/api/account/data")

    assert api.client.post("/api/analyze", json={"text": "across the pond"}).status_code == 200
