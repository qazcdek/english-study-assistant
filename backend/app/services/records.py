"""저장된 분석 기록을 지금 스키마로 올린다.

프롬프트를 손볼 때마다 결과 스키마가 바뀌는데, DB 에는 그때그때의 형식으로 저장돼 있다.
Pydantic 모델을 느슨하게 만들면 옛 기록은 읽히지만 **LLM 응답 검증까지 느슨해진다** —
모델이 필드를 빠뜨려도 조용히 통과한다. 그래서 모델은 엄격하게 두고,
읽을 때만 여기서 형식을 올린다.

새로 저장하는 기록에는 `schema_version` 을 함께 남긴다. 옛 기록에는 없으므로 0 으로 본다.
"""

from typing import Any

RESULT_VERSION = 3


def stamp(result: dict[str, Any]) -> dict[str, Any]:
    """저장 직전에 현재 버전을 찍는다."""
    return {**result, "schema_version": RESULT_VERSION}


def upgrade(result: dict[str, Any]) -> dict[str, Any]:
    """읽어 온 기록을 현재 스키마로 올린다.

    버전이 없으면 모양을 보고 판단한다. 버전을 찍기 전에 저장된 기록이 있기 때문이다.
    """
    data = dict(result)
    version = data.get("schema_version", 0)
    if version >= RESULT_VERSION:
        return data

    data["structures"] = [_upgrade_structure(s) for s in data.get("structures") or []]
    if data.get("overview"):
        data["overview"] = _upgrade_overview(data["overview"])
    data["expressions"] = [_upgrade_expression(e) for e in data.get("expressions") or []]
    data["schema_version"] = RESULT_VERSION
    return data


def _upgrade_structure(item: dict[str, Any]) -> dict[str, Any]:
    """구문 해설이 explanation 한 칸이던 시절의 기록.

    그 한 칸에 구조 이름·역할·등가 표현이 뭉쳐 있었다. 쪼갤 방법이 없으므로
    role(이 문장에서 하는 일) 자리에 그대로 둔다. name 은 비워 두고 화면에서 감춘다.
    """
    if "role" in item:
        return item
    return {
        "fragment": item.get("fragment", ""),
        "name": "",
        "role": item.get("explanation", ""),
        "rewrite": "",
        "pitfall": "",
    }


def _upgrade_overview(item: dict[str, Any]) -> dict[str, Any]:
    """총평에 frequency(사용 빈도)가 있고 tone 이 없던 시절의 기록.

    빈도 판단은 기준이 모호해 걷어냈다(04-prompt-design.md 7절). 값을 옮길 곳이 없으므로 버린다.
    """
    upgraded = {k: v for k, v in item.items() if k != "frequency"}
    upgraded.setdefault("tone", "")
    upgraded.setdefault("key_expressions", [])
    return upgraded


def _upgrade_expression(item: dict[str, Any]) -> dict[str, Any]:
    """nuance 가 없던 시절의 기록. 기본값이 있어 그대로 두어도 되지만 명시해 둔다."""
    return {**item, "nuance": item.get("nuance", "")}
