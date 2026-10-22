"""와이어 스키마 깎기와 되재기 (M12-T3).

제약을 **왜** 두 겹으로 거는지는 04-prompt-design.md §10.
"""

import pytest

from app.providers.schema import SchemaLimits, adapt, violations

WIDE = SchemaLimits()
NARROW = SchemaLimits(takes_max_items=False, min_items_allowed=(0, 1))


def array_schema(low: int, high: int, description: str = "") -> dict:
    items: dict = {
        "type": "array",
        "items": {"type": "string"},
        "minItems": low,
        "maxItems": high,
    }
    if description:
        items["description"] = description
    return {
        "type": "object",
        "properties": {"expressions": items},
        "required": ["expressions"],
        "additionalProperties": False,
    }


def inner(schema: dict) -> dict:
    return schema["properties"]["expressions"]


# ------------------------------------------------------------------ 깎지 않는 쪽


def test_a_provider_that_takes_everything_gets_the_schema_untouched():
    """깎을 것이 없으면 **같은 객체**를 그대로 쓴다.

    베끼기만 해도 결과는 같지만, 안 깎았다는 사실이 동일성으로 드러나야
    "이 제공자는 건드리지 않는다" 를 한 줄로 확인할 수 있다.
    """
    schema = array_schema(2, 8)

    assert adapt(schema, WIDE) is schema


def test_the_default_limits_take_everything():
    """**기본값은 "전부 받는다" 다.**

    기본값이 좁으면 구현이 안 채운 제공자에서 멀쩡한 제약이 조용히 사라진다.
    """
    assert WIDE.takes_max_items
    assert WIDE.keeps_min_items(7)


def test_a_narrow_provider_keeps_a_min_of_one():
    """`minItems: 1` 은 Anthropic 도 받는다. 받는 것은 빼지 않는다."""
    adapted = adapt(array_schema(1, 8), NARROW)

    assert inner(adapted)["minItems"] == 1


# -------------------------------------------------------------------- 깎는 쪽


def test_a_narrow_provider_loses_max_items_and_a_min_above_one():
    adapted = adapt(array_schema(3, 8), NARROW)

    assert "maxItems" not in inner(adapted)
    assert "minItems" not in inner(adapted)


def test_the_original_schema_is_not_mutated():
    """**원본을 건드리면 되재기가 무의미해진다.** 깎기 전 값으로 재야 한다."""
    schema = array_schema(3, 8)
    adapt(schema, NARROW)

    assert inner(schema)["minItems"] == 3
    assert inner(schema)["maxItems"] == 8


def test_what_was_dropped_is_said_in_the_description():
    """뗀 제약은 부탁으로라도 남는다 — 아무 말도 없으면 단서가 0 이다."""
    said = inner(adapt(array_schema(3, 8), NARROW))["description"]

    assert "3개" in said
    assert "8개" in said


def test_the_lower_bound_is_said_first():
    """"3개 이상 8개 이하" 순서로 읽혀야 한다. 뒤집히면 문장이 어색해진다."""
    said = inner(adapt(array_schema(3, 8), NARROW))["description"]

    assert said.index("3개") < said.index("8개")


def test_an_existing_description_is_kept():
    said = inner(adapt(array_schema(3, 8, "고른 표현"), NARROW))["description"]

    assert said.startswith("고른 표현")
    assert "3개" in said


def test_nested_arrays_are_reached():
    """파트 스키마는 한 겹 더 깊을 수 있다. 바깥만 보면 안쪽이 남는다."""
    schema = {
        "type": "object",
        "properties": {
            "overview": {
                "type": "object",
                "properties": {
                    "key_expressions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 3,
                    }
                },
            }
        },
    }

    adapted = adapt(schema, NARROW)
    deep = adapted["properties"]["overview"]["properties"]["key_expressions"]

    assert "maxItems" not in deep
    # minItems 1 은 받으므로 남는다.
    assert deep["minItems"] == 1


# -------------------------------------------------------------------- 되재기


def test_a_response_within_the_bounds_passes():
    assert violations(array_schema(2, 3), {"expressions": ["a", "b"]}) == []


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        (["a"], "2개 이상"),
        (["a", "b", "c", "d"], "3개 이하"),
    ],
)
def test_a_response_outside_the_bounds_is_caught(items, expected):
    found = violations(array_schema(2, 3), {"expressions": items})

    assert len(found) == 1
    assert expected in found[0]


def test_the_violation_says_where_and_how_many():
    """재시도 로그에 그대로 실린다. "어긋났다" 만으로는 고칠 단서가 없다."""
    found = violations(array_schema(2, 3), {"expressions": ["a"]})

    assert "expressions" in found[0]
    assert "1개" in found[0]


def test_a_missing_field_is_not_a_count_violation():
    """빠진 칸은 파이단틱이 잡는다. 여기서 또 잡으면 오류 메시지가 둘이 된다."""
    assert violations(array_schema(2, 3), {}) == []


def test_a_nested_count_is_measured():
    schema = {
        "type": "object",
        "properties": {
            "overview": {
                "type": "object",
                "properties": {
                    "key_expressions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 3,
                    }
                },
            }
        },
    }

    found = violations(schema, {"overview": {"key_expressions": ["a", "b", "c", "d"]}})

    assert len(found) == 1
    assert "key_expressions" in found[0]


def test_measuring_uses_the_original_not_the_adapted_schema():
    """**이 검사가 두 겹의 요점이다.**

    깎인 스키마로 재면 아무것도 안 걸린다 — 깎인 쪽에는 제약이 없으니까.
    그래서 분석기는 `adapt` 결과를 보내고 `violations` 에는 원본을 넘긴다.
    """
    wanted = array_schema(3, 8)
    sent = adapt(wanted, NARROW)
    answer = {"expressions": ["a"]}

    assert violations(wanted, answer) != []
    assert violations(sent, answer) == []
