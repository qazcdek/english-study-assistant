"""와이어 스키마가 실을 수 있는 것, 그리고 못 싣는 것을 대신 지키는 검사.

### 왜 이 파일이 생겼나

CLAUDE.md 6절 2항 — **"LLM 에 거는 제약은 부탁이 아니라 스키마로 건다. 다만
프로바이더마다 지키는 범위가 다르므로, 양쪽에서 도는 스키마에는 쓸 수 있는 것만 쓴다."**

제공자가 둘일 때는 교집합이 넓어서 신경 쓸 일이 없었다. 넷이 되니 갈린다 —
표현 개수를 강제하는 `minItems`/`maxItems` 가 바로 그 자리에 걸린다.

| | `minItems` | `maxItems` |
|---|---|---|
| llama-server | 문법으로 강제한다 | 강제한다 |
| Gemini (OpenAI 호환) | 받는다 | 받는다 |
| OpenAI (strict) | 받는다 | 받는다 |
| Anthropic (Messages) | **0 또는 1 만** | **받지 않는다 — 400** |

**출처를 밝힌다.** llama-server 와 Gemini 는 앱이 그걸로 돌고 있다는 사실이 근거다.
OpenAI 와 Anthropic 은 **문서를 읽은 것이고 호출해 확인하지 않았다** —
13-gemini-benchmark.md §2 와 같은 실측은 키가 있어야 한다.
이 두 겹을 왜 이렇게 나눴는지는 04-prompt-design.md §10.

### 두 겹으로 건다

전에는 한 겹이었다 — 스키마에 실어 보내면 끝. 그런데 **스키마가 못 싣는 제약은
아무도 안 지킨다.** 파이단틱 모델에는 개수 제약이 없다(개수가 난이도와 글 길이에
따라 달라서 정적 모델에 못 박는다). 즉 Anthropic 에서 제약을 떼면 **개수가 완전히
풀린다.** 검증을 느슨하게 해서 해결하는 꼴이고, CLAUDE.md 6절 4항이 막는 일이다.

그래서 떼는 것과 **대신 재는 것**을 한 파일에 둔다.

```
adapt()       프로바이더가 받는 것만 남겨 보낸다. 뗀 제약은 description 으로 옮긴다
violations()  돌아온 응답을 **원본 스키마**로 다시 재고, 어긋나면 재시도를 부른다
```

`violations()` 는 **프로바이더를 가리지 않고 돈다.** Anthropic 때문에 만들었지만
Gemini 가 개수를 어겨도 전에는 아무것도 안 잡았다 — 그쪽도 이제 잡힌다.

[문서] 04-prompt-design.md §10.2
[문서] plan/DONE.md M12-T3
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchemaLimits:
    """이 프로바이더의 와이어 스키마가 실을 수 있는 범위.

    **기본값은 "전부 받는다" 다.** 구현이 안 채워도 돌아야 하고, 안 채운 쪽이
    좁아지면 멀쩡한 제약이 조용히 사라진다. (가짜가 진짜보다 좁아서 테스트 전부가
    깨진 일이 있었다 — `base.py` 의 `model` 참고.)
    """

    takes_max_items: bool = True
    # 받아 주는 `minItems` 값. `None` 이면 전부 받는다.
    min_items_allowed: tuple[int, ...] | None = None

    def keeps_min_items(self, value: int) -> bool:
        return self.min_items_allowed is None or value in self.min_items_allowed


# 제약을 뗄 때 대신 적는 말. **부탁이 되지만, 부탁이라도 적는 쪽이 낫다** —
# 아무 말도 없으면 모델은 개수에 대한 단서를 하나도 못 받는다.
_MIN = "항목이 적어도 {n}개는 있어야 한다"
_MAX = "항목이 {n}개를 넘으면 안 된다"


def adapt(schema: dict[str, Any], limits: SchemaLimits) -> dict[str, Any]:
    """프로바이더가 받는 것만 남긴 스키마. 원본은 건드리지 않는다.

    뗀 제약은 그 배열의 `description` 뒤에 한국어 문장으로 붙는다.
    """
    if _unchanged(schema, limits):
        return schema
    return _walk(schema, limits)


def violations(schema: dict[str, Any], data: Any) -> list[str]:
    """응답이 **원본 스키마**의 개수 제약을 어긴 자리.

    빈 목록이면 통과다. 어긋난 자리마다 사람이 읽을 한 줄을 돌려준다 —
    재시도 로그와 오류 메시지에 그대로 실린다.
    """
    found: list[str] = []
    _check(schema, data, "", found)
    return found


# ----------------------------------------------------------------------- private


def _unchanged(node: Any, limits: SchemaLimits) -> bool:
    """뗄 것이 하나도 없나. 대부분의 파트가 여기서 끝나고 원본을 그대로 쓴다."""
    if not isinstance(node, dict):
        return True
    if "maxItems" in node and not limits.takes_max_items:
        return False
    if "minItems" in node and not limits.keeps_min_items(node["minItems"]):
        return False
    return all(_unchanged(child, limits) for child in _children(node))


def _children(node: dict[str, Any]) -> list[Any]:
    kids: list[Any] = []
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            kids.append(node[key])
    for key in ("properties", "$defs", "definitions"):
        if isinstance(node.get(key), dict):
            kids.extend(node[key].values())
    for key in ("anyOf", "allOf", "oneOf", "prefixItems"):
        if isinstance(node.get(key), list):
            kids.extend(node[key])
    return kids


def _walk(node: Any, limits: SchemaLimits) -> Any:
    if isinstance(node, list):
        return [_walk(item, limits) for item in node]
    if not isinstance(node, dict):
        return node

    out = {key: _walk(value, limits) for key, value in node.items()}

    dropped: list[str] = []
    if "maxItems" in out and not limits.takes_max_items:
        dropped.append(_MAX.format(n=out.pop("maxItems")))
    if "minItems" in out and not limits.keeps_min_items(out["minItems"]):
        dropped.append(_MIN.format(n=out.pop("minItems")))

    if dropped:
        # 하한을 먼저 읽히게 둔다. 뗀 쪽이 둘이면 "N개 이상 M개 이하" 순서가 된다.
        said = ". ".join(reversed(dropped)) + "."
        before = out.get("description", "")
        out["description"] = f"{before} {said}".strip()

    return out


def _check(node: Any, data: Any, path: str, found: list[str]) -> None:
    if not isinstance(node, dict):
        return

    if node.get("type") == "array" and isinstance(data, list):
        where = path or "응답"
        low, high = node.get("minItems"), node.get("maxItems")
        if isinstance(low, int) and len(data) < low:
            found.append(f"{where} 항목이 {len(data)}개다 — {low}개 이상이어야 한다")
        if isinstance(high, int) and len(data) > high:
            found.append(f"{where} 항목이 {len(data)}개다 — {high}개 이하여야 한다")
        item = node.get("items")
        for index, element in enumerate(data):
            _check(item, element, f"{where}[{index}]", found)
        return

    properties = node.get("properties")
    if isinstance(properties, dict) and isinstance(data, dict):
        for key, child in properties.items():
            if key in data:
                _check(child, data[key], f"{path}.{key}" if path else key, found)
