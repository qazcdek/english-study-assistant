"""파트별 분석 프롬프트와 JSON 스키마.

분석을 네 파트로 쪼개 각각 독립된 호출로 처리한다. 파트마다 스키마가 작아 모델이 지키기 쉽고,
한 파트가 실패해도 나머지는 살아남으며, 완성된 순서대로 화면에 흘려보낼 수 있다.

각 파트의 JSON 은 항상 `{"<field>": ...}` 한 겹으로 감싼 형태다 —
`app/schemas.py` 의 파트 모델과 1:1 대응한다. 한쪽을 바꾸면 다른 쪽도 바꾼다.

측정 메모: 사고(thinking)를 켜면 파트를 쪼갤수록 오히려 사고가 길어진다.
"표현만 뽑아라" 같은 열린 과제에서 모델이 후보를 끝없이 재검토하기 때문이다.
그래서 파트 프롬프트에도 개수와 판별 기준을 구체적으로 못박는다 (documents/05-benchmark.md).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.providers.base import ChatMessage
from app.schemas import (
    ExpressionsPart,
    OverviewPart,
    StructuresPart,
    TranslationPart,
)

EXPRESSION_TYPES = [
    "고급 어휘",
    "관용구",
    "Phrasal Verb",
    "연어(Collocation)",
    "문법 포인트",
    "구어 표현",
    "전문 용어",
]
FORMALITIES = ["매우 격식", "격식", "중립", "비격식", "속어에 가까움"]
STYLES = ["문어체", "구어체", "혼합"]

LEVEL_GUIDE = {
    "beginner": (
        "학습자는 초급이다. 문법 용어를 최소한으로 쓰고 풀어서 설명한다. "
        "표현은 가장 중요한 5개 이하, 구문 해설은 2개 이하로 줄인다."
    ),
    "intermediate": (
        "학습자는 중급이다. 일반적인 문법 용어를 써도 좋다. "
        "표현은 3~8개, 구문 해설은 2~4개가 적당하다."
    ),
    "advanced": (
        "학습자는 상급이다. 뉘앙스 차이, 어원, 비슷한 표현과의 비교까지 짚어 준다. "
        "표현은 5~10개, 구문 해설은 3~5개까지 다룰 수 있다."
    ),
}

SHARED_SYSTEM = """너는 한국인 영어 학습자를 돕는 영어 분석 전문가다.
주어진 영어 텍스트를 분석해, 지정된 JSON 스키마를 따르는 객체 하나만 출력한다.

공통 규칙:
- JSON 외의 텍스트, 인사말, 코드 펜스(```)를 절대 덧붙이지 않는다.
- 영어는 영어로, 설명은 모두 한국어로 쓴다.
- 설명은 "~이다 / ~한다" 체로 쓴다. "~입니다 / ~합니다" 체를 섞지 않는다.
- 확실하지 않은 정보는 지어내지 말고, 해당 항목을 빼거나 배열을 비운다.
- 정해진 개수 안에서 끝낸다. 후보를 끝없이 재검토하지 말고 판단이 서면 바로 출력한다.

{level_guide}

{task}"""

RETRY_NUDGE = (
    "직전 응답이 올바른 JSON이 아니었다. 이번에는 설명이나 코드 펜스 없이 "
    "스키마를 따르는 JSON 객체 하나만 출력하라."
)

# --------------------------------------------------------------------- 파트별 스키마

_EXPRESSION_ITEM = {
    "type": "object",
    "properties": {
        "expression": {"type": "string"},
        "type": {"type": "string", "enum": EXPRESSION_TYPES},
        "meaning": {"type": "string"},
        "example": {"type": "string"},
        "example_ko": {"type": "string"},
    },
    "required": ["expression", "type", "meaning"],
    "additionalProperties": False,
}

_STRUCTURE_ITEM = {
    "type": "object",
    "properties": {"fragment": {"type": "string"}, "explanation": {"type": "string"}},
    "required": ["fragment", "explanation"],
    "additionalProperties": False,
}

_OVERVIEW_OBJECT = {
    "type": "object",
    "properties": {
        "domain": {"type": "string"},
        "tone": {"type": "string"},
        "formality": {"type": "string", "enum": FORMALITIES},
        "style": {"type": "string", "enum": STYLES},
        "key_expressions": {"type": "array", "items": {"type": "string"}},
        "comment": {"type": "string"},
    },
    "required": ["domain", "tone", "formality", "style", "key_expressions", "comment"],
    "additionalProperties": False,
}


def _wrap(field: str, value_schema: dict) -> dict:
    """파트 응답은 항상 {"<field>": ...} 한 겹으로 감싼다."""
    return {
        "type": "object",
        "properties": {field: value_schema},
        "required": [field],
        "additionalProperties": False,
    }


# --------------------------------------------------------------------- 파트 정의


@dataclass(frozen=True)
class PartSpec:
    field: str
    title: str
    task: str
    schema: dict
    model: type
    build_user: Callable[[str, dict[str, Any]], str]


def _plain_user(instruction: str) -> Callable[[str, dict[str, Any]], str]:
    def build(text: str, _state: dict[str, Any]) -> str:
        return f"{instruction}\n\n---\n{text}\n---"

    return build


def _covered(state: dict[str, Any]) -> list[str]:
    return [e["expression"] for e in state.get("expressions", [])]


def _structures_user(text: str, state: dict[str, Any]) -> str:
    covered = _covered(state)
    note = ""
    if covered:
        # 표현 풀이 파트가 이미 다룬 어구를 구조 해설에서 되풀이하지 않게 한다.
        note = (
            "\n아래 표현은 표현 풀이에서 이미 다뤘다. 이 어구 자체를 fragment 로 삼지 말고, "
            "꼭 언급해야 한다면 더 큰 구조의 일부로만 다룬다.\n"
            f"이미 다룬 표현: {', '.join(covered)}\n"
        )
    return (
        "다음 텍스트에서 문법적으로 설명할 가치가 있는 구문을 해설해라."
        f"{note}\n---\n{text}\n---"
    )


def _overview_user(text: str, state: dict[str, Any]) -> str:
    picked = _covered(state)
    listed = ", ".join(picked) if picked else "(뽑힌 표현 없음)"
    return (
        "다음 텍스트가 어떤 분야에서 어떤 톤으로 쓰인 글인지 정리하고, "
        "아래 표현 목록 중 특히 챙길 것을 1~3개 고른다.\n"
        "key_expressions 의 각 값은 아래 목록에 있는 것과 글자 그대로 같아야 한다.\n\n"
        f"표현 목록: {listed}\n\n---\n{text}\n---"
    )


PART_SPECS: tuple[PartSpec, ...] = (
    PartSpec(
        field="translation",
        title="자연스러운 번역",
        task=(
            "이번 작업은 번역이다.\n"
            "- 직역이 아니라, 한국어로 자연스럽게 읽히는 번역을 쓴다.\n"
            "- 원문의 어조(격식/비격식, 진지함/가벼움)를 한국어에서도 살린다.\n"
            "- 번역문만 쓰고 해설은 붙이지 않는다."
        ),
        schema=_wrap("translation", {"type": "string"}),
        model=TranslationPart,
        build_user=_plain_user("다음 영어 텍스트를 번역해라."),
    ),
    PartSpec(
        field="expressions",
        title="표현 풀이",
        task=(
            "이번 작업은 표현 풀이다. 표의 각 칸에 들어갈 내용은 아래와 같다.\n"
            "\n"
            "[expression] — 표현 (영어)\n"
            "- 원문에 실제로 등장한 표현만 고른다. 사전에서 가져온 무관한 표현을 지어내지 않는다.\n"
            "- 원문의 활용형이 아니라 사전에 실릴 기본형으로 적는다.\n"
            '  원문이 "sums up" 이면 "sum up", "has been thrown at" 이면 "throw at" 으로 적는다.\n'
            "- 표현의 경계를 정확히 잡는다. 앞뒤 단어를 덧붙이거나 잘라내지 않는다.\n"
            '  "find its way across the pond" 가 아니라 "across the pond" 가 하나의 표현이다.\n'
            "- the, is, good 같이 학습 가치가 낮은 기초 어휘는 제외한다.\n"
            "- 같은 표현을 두 번 넣지 않는다.\n"
            "\n"
            "[type] — 유형\n"
            "- 아래 기준을 위에서부터 차례로 확인해, 처음 맞는 것 하나를 고른다.\n"
            '  "고급 어휘"는 다른 어디에도 해당하지 않을 때 쓰는 마지막 선택지다.\n'
            "  1. Phrasal Verb — 동사 + 부사/전치사 조합이고, 낱말 뜻의 합과 의미가 다르다.\n"
            "     예: sum up, throw at, come across, put off\n"
            "  2. 관용구 — 두 단어 이상의 굳어진 비유 표현으로, 직역하면 뜻이 통하지 않는다.\n"
            "     예: across the pond, take it on the chin, a piece of cake\n"
            "  3. 연어(Collocation) — 원어민이 습관적으로 함께 쓰는 자연스러운 단어 짝.\n"
            "     예: cope with, meet a deadline, heavy rain\n"
            "  4. 구어 표현 — 대화나 비격식 글에서 주로 쓰이는 표현. 예: wanna, gonna\n"
            "  5. 전문 용어 — 특정 분야(금융, 법률, 의학, 기술)의 용어.\n"
            "  6. 문법 포인트 — 단어의 뜻이 아니라 문법 형태 자체가 학습 대상일 때.\n"
            "     예: 접미사 -prone 으로 만든 복합 형용사\n"
            "  7. 고급 어휘 — 위 어디에도 해당하지 않는, 수준 높은 단일 단어.\n"
            "\n"
            "[meaning] — 의미 및 설명\n"
            "- 두 부분으로 쓴다. 먼저 한국어 뜻을 쓰고, 이어서 이 표현을 어떻게 다뤄야 하는지 짚는다.\n"
            "- 앞부분: 한국어 뜻. 유의어가 있으면 쉼표로 두세 개까지 덧붙인다.\n"
            "- 뒷부분: 아래 중 이 표현에 해당하는 것을 한 문장으로 쓴다.\n"
            "  · 주어진 원문에서 어떤 뜻으로 쓰였는지 (사전 뜻이 여럿일 때 특히 중요하다)\n"
            "  · 비유에서 나온 표현이면 무엇에 빗댄 말인지\n"
            '    예: across the pond — 대서양을 "연못"에 빗댄 표현\n'
            "  · 함께 쓰이는 전치사나 문형이 정해져 있다면 그 형태\n"
            "    예: weigh in on ~ 처럼 on 과 함께 쓴다\n"
            "  · 격식/비격식처럼 쓸 자리가 제한된다면 그 점\n"
            "- 사전 뜻만 나열하고 끝내지 않는다. 두세 줄을 넘기지도 않는다.\n"
            "\n"
            "[example] / [example_ko] — 예문과 그 한국어 뜻\n"
            "- example 은 원문과 다른 맥락에서 그 표현을 쓴 5~12 단어의 짧은 영어 문장.\n"
            "- 원문 문장을 그대로 다시 쓰지 않는다.\n"
            "- 어순이나 전치사가 조금이라도 헷갈리면 예문을 아예 생략한다. 틀린 예문은 없는 것만 못하다.\n"
            "- 특히 목적어를 사이에 넣을 수 있는 구동사는 어순을 확신할 때만 쓴다.\n"
            '  "throw many reviews at the film" 은 맞지만 "throw at the film many reviews" 는 틀렸다.\n'
            "- 원어민이 실제로 쓸 법한 자연스러운 문장만 넣는다.\n"
            "- example 을 넣었다면 example_ko 에 그 문장의 한국어 뜻을 반드시 함께 넣는다.\n"
            "  학습자가 이 한국어만 보고 영어 문장을 복원하는 연습에 쓰이므로, "
            "영어 문장의 정보가 빠짐없이 담긴 자연스러운 한국어여야 한다.\n"
            "- example 을 생략하면 example_ko 도 넣지 않는다."
        ),
        schema=_wrap("expressions", {"type": "array", "items": _EXPRESSION_ITEM}),
        model=ExpressionsPart,
        build_user=_plain_user("다음 텍스트에서 학습 가치가 있는 표현을 뽑아라."),
    ),
    PartSpec(
        field="structures",
        title="문장 구조",
        task=(
            "이번 작업은 구문 해설이다. 무엇을 고르고 어떻게 쓸지는 아래와 같다.\n"
            "\n"
            "[무엇을 고를 것인가]\n"
            "- 단어 뜻을 다 알아도 문장 구조가 잡히지 않는 지점을 고른다. 이것이 유일한 선정 기준이다.\n"
            "- 특히 다음을 우선한다.\n"
            "  · 어순이 뒤집히거나 접속사·관계사가 생략된 곳 (Had she known..., the book I read)\n"
            "  · 형식주어 it, 유도부사 there 처럼 자리만 채우는 말이 있는 곳\n"
            "  · 명사 뒤에 길게 붙은 수식구 (관계절, 분사구, 전치사구)\n"
            "    한국어는 수식어가 명사 앞에 오므로 이 부분에서 수식 관계를 놓치기 쉽다\n"
            "  · 주어가 겉으로 드러나지 않는 절 (분사구문, to부정사구) — 숨은 주어가 무엇인지 짚어 준다\n"
            "  · 가정법, 행위자를 일부러 감춘 수동태, 부정어나 한정어의 범위가 헷갈리는 곳\n"
            "- 다음은 다루지 않는다.\n"
            "  · 단어나 숙어의 뜻. 그것은 표현 풀이 파트가 맡는다.\n"
            "    wanna, bail on, I get it 같은 어휘 항목을 여기에 넣지 않는다.\n"
            "  · 3인칭 단수 일치처럼 알아도 독해가 달라지지 않는 문법 사실\n"
            "  · 같은 구조를 범위만 바꿔 두 번 넣는 것\n"
            "\n"
            "[fragment] — 원문 조각\n"
            "- 구조가 드러나는 최소 범위만 원문 그대로 인용한다. 문장 전체를 통째로 넣지 않는다.\n"
            "- 설명하려는 구조가 fragment 안에 온전히 들어 있어야 한다.\n"
            "  분사구문을 설명하면서 문장 전체를 인용하면 안 되고, 분사구만 잘라 인용한다.\n"
            "- 항목끼리 인용 범위가 겹치지 않게 한다.\n"
            "\n"
            "[explanation] — 해설\n"
            "- 아래 세 가지를 순서대로 쓴다.\n"
            "  1. 이 구조의 이름. 표준 문법 용어를 정확히 쓴다.\n"
            "     (예: if 를 생략한 도치 가정법, 형식주어 it, 명사를 뒤에서 꾸미는 관계절)\n"
            "  2. 그 구조가 이 문장에서 하는 일. 문법 일반론이 아니라 이 문장에 대해 쓴다.\n"
            "     수동태라면 '수동태는 대상에 초점을 둔다' 가 아니라, "
            "이 문장에서 행위자를 왜 밝히지 않았는지를 쓴다.\n"
            "  3. 쉬운 말로 바꿔 쓴 등가 표현, 또는 한국어 화자가 틀리기 쉬운 오독 지점.\n"
            '     (예: "Had she known" 은 "If she had known" 과 같다)\n'
            "- \"고급스러운 표현이다\", \"문장을 자연스럽게 만든다\" 같은 평가는 쓰지 않는다.\n"
            "- 위 세 가지를 각각 한 문장으로, 전체 세 문장 안에서 끝낸다. "
            "문법 규칙을 일반론으로 늘어놓지 않는다."
        ),
        schema=_wrap("structures", {"type": "array", "items": _STRUCTURE_ITEM}),
        model=StructuresPart,
        build_user=_structures_user,
    ),
    PartSpec(
        field="overview",
        title="총평",
        task=(
            "이번 작업은 총평이다. 이 글이 어떤 분야에서 어떤 톤으로 쓰였고, "
            "무엇을 챙겨 가야 하는지 정리한다. 표현이 얼마나 흔한지 같은 빈도 판단은 하지 않는다.\n"
            "\n"
            "[domain] — 분야\n"
            "- 이 글이 어디에 실릴 법한 글인지 쓴다.\n"
            "  예: 경제 신문 칼럼, 임상 연구 논문, 개발자용 기술 문서, 친구 간 메신저 대화\n"
            "- 글의 주제나 글쓴이의 목적이 아니다. "
            '"일상적 갈등 해결" 같은 상황 묘사가 아니라 글의 종류를 쓴다.\n'
            "- 본문에 근거가 없는 장르를 추측하지 않는다. 확실하지 않으면 좁히지 말고 넓게 쓴다.\n"
            "\n"
            "[tone] — 톤\n"
            "- 글쓴이가 독자를 대하는 태도를 쓴다.\n"
            "  예: 단정적인, 조심스럽게 유보하는, 가볍게 비꼬는, 몰아붙이며 설득하는, "
            "담담히 사실만 전하는\n"
            '- "격식", "비격식", "문어체", "구어체" 라는 낱말을 쓰지 않는다. '
            "그것은 아래 두 칸이 이미 맡는다.\n"
            "\n"
            "[formality] / [style] — 격식 수준과 문체\n"
            "- 인상이 아니라 본문에 있는 표지를 근거로 고른다.\n"
            "  · 비격식·구어체 쪽 표지: 축약형(wanna, gonna, don't), 속어, 감탄사, "
            "독자에게 말 거는 you, 줄표나 말줄임\n"
            "  · 격식·문어체 쪽 표지: 수동태, 명사화된 표현, 긴 후치 수식, 전문 용어, "
            "일인칭이 드러나지 않음\n"
            "\n"
            "[key_expressions] — 꼭 챙길 표현\n"
            "- 위에서 받은 표현 목록에 있는 것만 고른다. 목록에 없는 말을 새로 만들지 않는다.\n"
            "- 이 글을 이해하는 데 가장 중요한 것 1~3개.\n"
            "\n"
            "[comment] — 코멘트\n"
            "- 아래 세 가지를 담되 3~4문장을 넘기지 않는다.\n"
            "  1. 고른 표현들이 이 글에서 왜 핵심인지.\n"
            "  2. 그중 학습자가 직접 써도 되는 것과, 뜻만 알아두면 되는 것을 구분해 준다.\n"
            "     격식 있는 글이나 시험 답안에서 피해야 할 표현이 있으면 반드시 짚는다.\n"
            "  3. 어떤 상황에서 써먹을 수 있는지.\n"
            "- 작품 해설이나 문체 비평으로 흐르지 않는다. 학습자가 무엇을 하면 되는지를 쓴다."
        ),
        schema=_wrap("overview", _OVERVIEW_OBJECT),
        model=OverviewPart,
        build_user=_overview_user,
    ),
)

PART_FIELDS = tuple(spec.field for spec in PART_SPECS)


def build_messages(
    spec: PartSpec,
    text: str,
    level: str = "intermediate",
    state: dict[str, Any] | None = None,
    *,
    retry: bool = False,
) -> list[ChatMessage]:
    system = SHARED_SYSTEM.format(
        level_guide=LEVEL_GUIDE.get(level, LEVEL_GUIDE["intermediate"]),
        task=spec.task,
    )
    if retry:
        system = f"{system}\n\n{RETRY_NUDGE}"
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=spec.build_user(text, state or {})),
    ]

