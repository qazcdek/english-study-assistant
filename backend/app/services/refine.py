"""LLM 응답을 코드로 다듬는다.

프롬프트로 부탁해도 가끔 새는 것들이 있다. 여기서 잡는 것은
**추가 LLM 호출 없이, 규칙만으로 확실히 판별되는 것**뿐이다.
판단이 필요한 일(무엇이 더 좋은 표현인가)은 여기서 하지 않는다.

- 따옴표·공백 정리
- 다어절 표현을 낱개로 쪼갠 중복 제거 ("a blend of" 와 "blend" 가 함께 나온 경우)
- 범위가 겹치는 구문 해설 제거 ("Once the migration has been applied" 와 "has been applied")
- key_expressions 가 표에 없는 표현을 가리키는 경우 정리
"""

import re
from typing import TypeVar

from app.schemas import Expression, Overview, StructureNote

_QUOTES = "\"'“”‘’「」"
_NON_WORD = re.compile(r"[^0-9a-z]+")

T = TypeVar("T")


def _strip(text: str) -> str:
    """앞뒤 공백과 감싼 따옴표를 걷어낸다. UI 가 따로 따옴표를 붙이므로 중복을 막는다."""
    cleaned = text.strip()
    while len(cleaned) >= 2 and cleaned[0] in _QUOTES and cleaned[-1] in _QUOTES:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _tokens(text: str) -> list[str]:
    return [t for t in _NON_WORD.sub(" ", text.lower()).split() if t]


def _key(text: str) -> str:
    return " ".join(_tokens(text))


def _is_sublist(inner: list[str], outer: list[str]) -> bool:
    """inner 가 outer 안에 연속으로 들어 있는가."""
    if not inner or len(inner) >= len(outer):
        return False
    return any(outer[i : i + len(inner)] == inner for i in range(len(outer) - len(inner) + 1))


def _dedupe(items: list[T], text_of) -> list[T]:
    """같은 표현의 중복과, 다어절 표현을 낱개로 쪼갠 조각을 없앤다.

    쪼갠 조각은 **한 낱말짜리일 때만** 지운다. 두 낱말 이상이면 서로 다른 표현일 수 있어
    섣불리 지우면 멀쩡한 항목을 잃는다.
    """
    kept: list[T] = []
    seen: set[str] = set()

    for item in items:
        key = _key(text_of(item))
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(item)

    token_lists = [_tokens(text_of(i)) for i in kept]
    drop: set[int] = set()
    for i, inner in enumerate(token_lists):
        if len(inner) != 1:
            continue
        if any(j != i and _is_sublist(inner, outer) for j, outer in enumerate(token_lists)):
            drop.add(i)

    return [item for i, item in enumerate(kept) if i not in drop]


def clean_expressions(items: list[Expression]) -> list[Expression]:
    for e in items:
        e.expression = _strip(e.expression)
        e.meaning = _strip(e.meaning)
        e.example = _strip(e.example) if e.example else None
        e.example_ko = _strip(e.example_ko) if e.example_ko else None
        # 예문만 있고 한국어 제시문이 없으면 작문 연습을 할 수 없다. 짝을 맞춘다.
        if not e.example or not e.example_ko:
            e.example = e.example_ko = None

    return _dedupe(items, lambda e: e.expression)


def clean_structures(items: list[StructureNote]) -> list[StructureNote]:
    for s in items:
        s.fragment = _strip(s.fragment)
        s.name = _strip(s.name)
        s.role = _strip(s.role)
        s.rewrite = _strip(s.rewrite)
        s.pitfall = _strip(s.pitfall)

    # 구문 해설은 항목끼리 인용 범위가 겹치면 안 된다. 짧은 쪽을 버린다.
    kept: list[StructureNote] = []
    seen: set[str] = set()
    for s in items:
        key = _key(s.fragment)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(s)

    token_lists = [_tokens(s.fragment) for s in kept]
    drop = {
        i
        for i, inner in enumerate(token_lists)
        if any(j != i and _is_sublist(inner, outer) for j, outer in enumerate(token_lists))
    }
    return [s for i, s in enumerate(kept) if i not in drop]


def align_key_expressions(overview: Overview, expressions: list[dict]) -> Overview:
    """표에 없는 표현을 가리키면 버리고, 표기가 다르면 표의 값으로 맞춘다."""
    canonical = {_key(e["expression"]): e["expression"] for e in expressions}
    aligned: list[str] = []
    for picked in overview.key_expressions:
        match = canonical.get(_key(picked))
        if match and match not in aligned:
            aligned.append(match)
    overview.key_expressions = aligned
    return overview


def apply(field: str, value, state: dict):
    """AnalyzerService 가 파트 결과를 받는 즉시 부르는 진입점."""
    if field == "expressions":
        return clean_expressions(value)
    if field == "structures":
        return clean_structures(value)
    if field == "overview":
        return align_key_expressions(value, state.get("expressions", []))
    return value
