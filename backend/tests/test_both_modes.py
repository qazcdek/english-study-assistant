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


# ------------------------------------------------------ 나의 표현과 연습 기록

PRACTICE = {
    "expression": "across the pond",
    "type": "관용구",
    "meaning": "대서양을 건너",
    "prompt_ko": "그녀의 소설은 대서양을 건너갔다.",
    "model_answer": "Her novel made it across the pond.",
    "learner_answer": "Her novel went across the pond",
    "source_text": "Her novel made it across the pond last year.",
}


def test_practice_is_saved(both_modes):
    """모드와 무관하다. 전에는 cloud 쪽에만 있어서 local 이 깨져도 안 잡혔다."""
    api = both_modes
    assert api.client.post("/api/practice", json=PRACTICE).status_code == 200

    rows = api.client.get("/api/practice/history").json()
    assert len(rows) == 1
    assert rows[0]["expression"] == "across the pond"
    assert rows[0]["verdict"] == "통함"


def test_practising_puts_the_expression_in_my_list(both_modes):
    """연습 기록은 나의 표현을 통해서만 닿는다. 안 올라가면 기록이 안 보인다."""
    api = both_modes
    api.client.post("/api/practice", json=PRACTICE)

    rows = api.client.get("/api/vocabulary").json()
    assert [r["expression"] for r in rows] == ["across the pond"]
    assert rows[0]["practice_count"] == 1
    # 연습 요청이 들고 온 값으로 칸이 채워진다 — 별을 안 눌렀어도 목록이 읽을 만하다.
    assert rows[0]["type"] == "관용구"
    assert rows[0]["example"] == PRACTICE["model_answer"]
    assert rows[0]["example_ko"] == PRACTICE["prompt_ko"]


def test_practising_does_not_overwrite_a_richer_entry(both_modes):
    """별로 담아 둔 풍부한 행을 연습 요청의 빈 값이 덮으면 목록이 가난해진다."""
    api = both_modes
    api.client.post(
        "/api/vocabulary",
        json={
            "expression": "across the pond",
            "type": "관용구",
            "meaning": "대서양을 건너 — 영국과 미국 사이를 가리킨다",
            "example": "Her novel made it across the pond.",
            "example_ko": "그녀의 소설은 대서양을 건너갔다.",
            "source_text": "원문 전체",
        },
    )
    api.client.post("/api/practice", json={**PRACTICE, "meaning": "", "source_text": ""})

    row = api.client.get("/api/vocabulary").json()[0]
    assert row["meaning"] == "대서양을 건너 — 영국과 미국 사이를 가리킨다"
    assert row["source_text"] == "원문 전체"


def test_removing_an_expression_takes_its_practice_history(both_modes):
    """남겨 두면 어느 화면에도 안 나타나는 유령 데이터가 된다."""
    api = both_modes
    api.client.post("/api/practice", json=PRACTICE)
    api.client.post("/api/practice", json=PRACTICE)
    item_id = api.client.get("/api/vocabulary").json()[0]["id"]

    removed = api.client.delete(f"/api/vocabulary/{item_id}").json()
    assert removed["practices_deleted"] == 2
    assert removed["expression"] == "across the pond"

    assert api.client.get("/api/vocabulary").json() == []
    assert api.client.get("/api/practice/history").json() == []


def test_removing_one_expression_keeps_another(both_modes):
    """연쇄 삭제가 표현 경계를 넘으면 안 된다."""
    api = both_modes
    api.client.post("/api/practice", json=PRACTICE)
    api.client.post("/api/practice", json={**PRACTICE, "expression": "sum up"})

    rows = {r["expression"]: r["id"] for r in api.client.get("/api/vocabulary").json()}
    api.client.delete(f"/api/vocabulary/{rows['across the pond']}")

    left = api.client.get("/api/practice/history").json()
    assert [r["expression"] for r in left] == ["sum up"]


def test_practice_history_can_be_narrowed_to_one_expression(both_modes):
    """목록에서 한 항목을 펼칠 때 그 표현의 기록만 가져온다."""
    api = both_modes
    api.client.post("/api/practice", json=PRACTICE)
    api.client.post("/api/practice", json={**PRACTICE, "expression": "sum up"})

    rows = api.client.get("/api/practice/history", params={"expression": "sum up"}).json()
    assert [r["expression"] for r in rows] == ["sum up"]
