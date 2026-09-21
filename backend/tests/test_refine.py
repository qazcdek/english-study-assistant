"""LLM 응답을 코드로 다듬는 규칙.

여기 사례는 전부 실제 출력에서 관찰된 것이다.
"""

from app.schemas import Expression, Overview, StructureNote
from app.services import refine


def expr(expression: str, **kw) -> Expression:
    return Expression(expression=expression, type=kw.pop("type", "고급 어휘"),
                      meaning=kw.pop("meaning", "뜻"), **kw)


def note(fragment: str) -> StructureNote:
    return StructureNote(fragment=fragment, name="이름", role="역할")


# --------------------------------------------------------------- 쪼갠 조각 제거


def test_single_word_split_from_multiword_is_dropped():
    """상급에서 'a blend of' 를 'blend' 로 쪼개 함께 내보내던 문제."""
    kept = refine.clean_expressions([expr("a blend of"), expr("blend")])

    assert [e.expression for e in kept] == ["a blend of"]


def test_split_detection_ignores_articles_and_case():
    kept = refine.clean_expressions([expr("Market Volatility"), expr("volatility")])

    assert [e.expression for e in kept] == ["Market Volatility"]


def test_multiword_expressions_are_never_dropped_as_fragments():
    """두 낱말 이상은 서로 다른 표현일 수 있어 섣불리 지우지 않는다."""
    kept = refine.clean_expressions(
        [expr("never have set foot in the house"), expr("set foot in")]
    )

    assert len(kept) == 2


def test_exact_duplicates_are_removed():
    kept = refine.clean_expressions([expr("sum up"), expr("Sum Up"), expr("sum  up")])

    assert [e.expression for e in kept] == ["sum up"]


def test_unrelated_expressions_are_kept():
    kept = refine.clean_expressions([expr("across the pond"), expr("sum up"), expr("resilience")])

    assert len(kept) == 3


# --------------------------------------------------------------- 따옴표·공백


def test_wrapping_quotes_are_stripped():
    """모델이 예문을 따옴표로 감싸 보내는데, UI 가 따로 따옴표를 붙여 겹쳐 보였다."""
    kept = refine.clean_expressions(
        [expr("  sum up  ", example='"He summed it up."', example_ko="“그가 요약했다.”")]
    )

    assert kept[0].expression == "sum up"
    assert kept[0].example == "He summed it up."
    assert kept[0].example_ko == "그가 요약했다."


def test_example_without_korean_prompt_is_dropped():
    """작문 연습은 한국어 제시문이 있어야 가능하다. 짝이 안 맞으면 둘 다 버린다."""
    kept = refine.clean_expressions([expr("sum up", example="He summed it up.")])

    assert kept[0].example is None
    assert kept[0].example_ko is None


# --------------------------------------------------------------- 구문 해설


def test_overlapping_structure_ranges_are_merged():
    """'Once the migration has been applied' 와 'has been applied' 가 따로 나오던 문제."""
    kept = refine.clean_structures(
        [note("Once the migration has been applied"), note("has been applied")]
    )

    assert [s.fragment for s in kept] == ["Once the migration has been applied"]


def test_separate_structures_are_kept():
    kept = refine.clean_structures([note("Had she known"), note("would never have set foot")])

    assert len(kept) == 2


# --------------------------------------------------------------- key_expressions


def overview(keys: list[str]) -> Overview:
    return Overview(domain="분야", tone="톤", formality="격식", style="문어체",
                    key_expressions=keys, comment="코멘트")


def test_key_expressions_not_in_table_are_dropped():
    result = refine.align_key_expressions(
        overview(["across the pond", "없는 표현"]), [{"expression": "across the pond"}]
    )

    assert result.key_expressions == ["across the pond"]


def test_key_expressions_are_aligned_to_table_spelling():
    """표에는 'Market Volatility' 인데 총평이 'market volatility' 로 쓰면 ★ 표시가 어긋난다."""
    result = refine.align_key_expressions(
        overview(["market volatility"]), [{"expression": "Market Volatility"}]
    )

    assert result.key_expressions == ["Market Volatility"]


def test_duplicate_key_expressions_are_removed():
    result = refine.align_key_expressions(
        overview(["sum up", "Sum Up"]), [{"expression": "sum up"}]
    )

    assert result.key_expressions == ["sum up"]
