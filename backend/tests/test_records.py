"""저장된 기록을 지금 스키마로 올리기.

여기 사례는 전부 실제로 DB 에 저장된 적 있는 형식이다.
프롬프트를 손볼 때마다 결과 스키마가 바뀌었는데 하위 호환을 챙기지 않아
옛 기록을 열면 500 이 났다.
"""

from app.schemas import AnalysisResult
from app.services.records import RESULT_VERSION, stamp, upgrade

BASE = {"source_text": "t", "translation": "번역", "expressions": [], "structures": [], "overview": None}


def test_structures_from_before_the_four_way_split():
    old = {**BASE, "structures": [{"fragment": "Had she known", "explanation": "도치 가정법이다."}]}

    result = AnalysisResult.model_validate(upgrade(old))

    note = result.structures[0]
    assert note.fragment == "Had she known"
    # 한 칸에 뭉쳐 있던 설명은 쪼갤 수 없다. 이 문장에서 하는 일 자리에 그대로 둔다.
    assert note.role == "도치 가정법이다."
    assert note.name == ""
    assert note.rewrite == note.pitfall == ""


def test_overview_from_before_the_frequency_removal():
    old = {
        **BASE,
        "overview": {
            "frequency": "자주",
            "formality": "격식",
            "style": "문어체",
            "domain": "칼럼",
            "comment": "코멘트",
        },
    }

    result = AnalysisResult.model_validate(upgrade(old))

    assert result.overview is not None
    assert result.overview.tone == ""
    assert result.overview.key_expressions == []
    # 빈도 판단은 기준이 모호해 걷어냈다. 옮길 곳이 없으므로 버린다.
    assert not hasattr(result.overview, "frequency")


def test_expressions_from_before_nuance():
    old = {**BASE, "expressions": [{"expression": "sum up", "type": "Phrasal Verb", "meaning": "요약하다"}]}

    result = AnalysisResult.model_validate(upgrade(old))

    assert result.expressions[0].nuance == ""


def test_current_records_pass_through_untouched():
    current = stamp({**BASE, "translation": "그대로"})

    assert upgrade(current) == current
    assert current["schema_version"] == RESULT_VERSION


def test_upgrade_does_not_mutate_the_stored_dict():
    """DB 에서 읽어 온 dict 를 그 자리에서 고치면 SQLAlchemy 가 변경으로 오해할 수 있다."""
    old = {**BASE, "structures": [{"fragment": "f", "explanation": "e"}]}
    snapshot = {**old, "structures": [dict(old["structures"][0])]}

    upgrade(old)

    assert old["structures"][0] == snapshot["structures"][0]
    assert "schema_version" not in old
