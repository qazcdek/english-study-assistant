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
    # 지워진 기록은 404 다. 전에는 400 이었다 (H-012).
    gone = api.client.get(f"/api/history/{record_id}")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "not_found"


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


# --------------------------------------------- 고를 수 있는 제공자 (M12-T1)


def test_config_tells_which_providers_this_mode_can_choose(both_modes):
    """**프론트가 목록을 들고 있지 않다.** 서버가 정한 것을 그대로 그린다 —
    프론트에 적으면 모드가 바뀔 때 어긋난다 (09 §3.2)."""
    api = both_modes
    config = api.client.get("/api/config").json()

    ids = [p["id"] for p in config["providers"]]
    assert ids, "고를 수 있는 제공자가 비었다"
    assert config["default_provider"] in ids

    if api.mode == "cloud":
        # llama-server 는 내 PC 에 있어서 Render 에서 닿지 않는다.
        assert "llama" not in ids
    else:
        # 사용자가 정한 규칙 — local 은 llama-server 와 cloud LLM 전부.
        assert "llama" in ids and "gemini" in ids


def test_config_says_which_providers_need_a_key(both_modes):
    """키가 필요한지 모르면 화면이 등록 칸을 그릴지 정할 수 없다."""
    api = both_modes
    by_id = {p["id"]: p for p in api.client.get("/api/config").json()["providers"]}

    for provider in by_id.values():
        if provider["needs_key"]:
            assert provider["key_url"], provider["id"]
    if api.mode == "local":
        assert by_id["llama"]["needs_key"] is False


# ------------------------------- 제공자·모델 선택과 키 (M12-T4, 두 모드)
#
# 전에는 이 엔드포인트가 **cloud 전용인 `auth` 라우터**에 있었다. 그래서
# **로컬에서는 Gemini 를 고를 수도 키를 넣을 수도 없었다** — 사용자가 요청한 것의
# 절반이 동작하지 않는 상태였다. 두 모드에서 돌아야 한다.


def test_settings_say_what_we_work_with(both_modes):
    api = both_modes
    settings = api.client.get("/api/account/settings").json()

    expected = "llama" if api.mode == "local" else "gemini"
    assert settings["active_provider"] == expected
    assert settings["active_model"]
    # local 은 llama-server 라 키가 필요 없고, cloud 픽스처는 Gemini 키를 넣어 둔다.
    # 둘 다 바로 쓸 수 있는 상태다 — 이유가 다르다.
    assert settings["ready"] is True


def test_choosing_a_provider_sticks(both_modes):
    """**회원 전역 설정이다.** 저장하면 그 뒤의 모든 작업이 그것으로 간다."""
    api = both_modes
    chosen = api.client.put(
        "/api/account/settings", json={"provider": "gemini"}
    ).json()

    assert chosen["active_provider"] == "gemini"
    assert api.client.get("/api/account/settings").json()["active_provider"] == "gemini"


def test_local_can_choose_gemini(both_modes):
    """사용자가 요청한 것 — *"로컬 모드에서도 gemini 모델을 사용할 수 있도록"*."""
    api = both_modes
    if api.mode != "local":
        return

    assert api.client.put("/api/account/settings", json={"provider": "gemini"}).status_code == 200


def test_cloud_cannot_choose_llama_server(both_modes):
    """내 PC 의 서버다. Render 에서 닿지 않는다."""
    api = both_modes
    response = api.client.put("/api/account/settings", json={"provider": "llama"})

    assert response.status_code == (200 if api.mode == "local" else 400)


def test_a_model_the_provider_does_not_offer_is_refused(both_modes):
    api = both_modes
    response = api.client.put(
        "/api/account/settings", json={"provider": "gemini", "model": "없는-모델"}
    )

    assert response.status_code == 400


def test_a_key_can_be_deleted_per_provider(both_modes):
    """키를 지워도 **다른 제공자 키는 남는다.** 한 칸이던 시절에는 하나뿐이었다."""
    api = both_modes
    before = api.client.get("/api/account/settings").json()["keys"]

    after = api.client.delete("/api/account/api-key", params={"provider": "gemini"}).json()

    assert "gemini" not in after["keys"]
    # cloud 픽스처는 Gemini 키를 넣어 두므로 지워진 것이 확인된다.
    if api.mode == "cloud":
        assert "gemini" in before


def test_a_provider_that_needs_no_key_refuses_one(both_modes):
    """llama-server 에 키를 넣으려는 것은 오해다. 조용히 받아 두면 오해가 굳는다."""
    api = both_modes
    response = api.client.put(
        "/api/account/api-key", json={"provider": "llama", "api_key": "x" * 20}
    )

    assert response.status_code == 400


def test_a_key_for_a_provider_that_is_not_ready_is_refused(both_modes):
    api = both_modes
    response = api.client.put(
        "/api/account/api-key", json={"provider": "anthropic", "api_key": "x" * 20}
    )

    assert response.status_code == 400


def test_storing_a_key_locally_needs_an_encryption_key(both_modes, monkeypatch):
    """**로컬에도 ENCRYPTION_KEY 가 필요해졌다.**

    전에는 로컬이 키를 저장한 적이 없어서 cloud 전용이었다. 이제 로컬에서도 cloud LLM
    을 고를 수 있으므로 그 키를 보관해야 하고, 보관한다면 암호화해야 한다.
    다만 **llama-server 만 쓰는 로컬에는 여전히 필요 없다** — 그래서 설정을 항상
    요구하지 않고 저장하려 할 때 안내한다.
    """
    from app.config import get_settings

    api = both_modes
    monkeypatch.setenv("ENCRYPTION_KEY", "")
    get_settings.cache_clear()

    response = api.client.put(
        "/api/account/api-key", json={"provider": "gemini", "api_key": "x" * 20}
    )

    assert response.status_code == 400
    assert "ENCRYPTION_KEY" in response.json()["error"]["message"]
