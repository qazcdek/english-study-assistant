"""작문 연습 채점 프롬프트.

예문을 가린 채 한국어 제시문만 보고 학습자가 쓴 영어 문장을 채점한다.

설계 근거 (documents/06-practice.md):
- 모범 답안과 다른 문장도 자연스럽고 뜻이 맞으면 정답이다. 이것이 가장 큰 오판 지점이라
  프롬프트 맨 앞에 못박는다.
- 피드백은 목표 표현에 집중한다. 관사·구두점까지 전부 지적하면 학습자가 압도된다.
  부차적 지적은 최대 2개로 제한한다.
- 잘한 점을 먼저 짚는다. 무엇을 유지해야 할지 알려 주는 정보이기도 하다.
- 고쳐 쓰기만 하지 않고 왜 그런지 설명한다(메타언어적 피드백).
"""

from app.providers.base import ChatMessage

VERDICTS = ["정확함", "통함", "다시"]

PRACTICE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": VERDICTS},
        "uses_target": {"type": "boolean"},
        "good_point": {"type": "string"},
        "target_note": {"type": "string"},
        "corrected": {"type": "string"},
        "other_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "uses_target", "good_point", "target_note", "corrected", "other_notes"],
    "additionalProperties": False,
}

LEVEL_GUIDE = {
    "beginner": "학습자는 초급이다. 문법 용어를 최소한으로 쓰고 풀어서 설명한다.",
    "intermediate": "학습자는 중급이다. 일반적인 문법 용어를 써도 좋다.",
    "advanced": "학습자는 상급이다. 뉘앙스 차이까지 짚어 준다.",
}

SYSTEM_PROMPT = """너는 한국인 영어 학습자의 영작문을 봐 주는 선생이다.
학습자는 한국어 제시문만 보고 목표 표현을 써서 영어 문장을 작성했다.
채점 결과를 지정된 JSON 스키마를 따르는 객체 하나로 출력한다.

가장 중요한 원칙:
- **모범 답안은 하나의 예일 뿐이다.** 학습자 문장이 모범 답안과 달라도,
  영어로 자연스럽고 제시문의 뜻을 담고 있으면 "정확함"으로 판정한다.
  단어 선택이나 문장 구조가 다르다는 이유로 깎지 않는다.
- 이 연습의 목적은 목표 표현을 직접 써 보는 것이다. 목표 표현을 쓰지 않았거나
  용법이 틀렸다면 그것이 핵심 지적 사항이다.

공통 규칙:
- JSON 외의 텍스트, 인사말, 코드 펜스(```)를 절대 덧붙이지 않는다.
- 설명은 한국어로, "~이다 / ~한다" 체로 쓴다. "~입니다 / ~합니다" 체를 섞지 않는다.

각 칸에 들어갈 내용:

[verdict] — 판정
- "정확함": 목표 표현을 바르게 썼고, 문장이 문법적으로 맞으며 원어민이 쓸 법하다.
- "통함": 뜻은 전달되지만 어색하거나, 목표 표현의 용법이 살짝 어긋난다.
- "다시": 목표 표현을 쓰지 않았거나 틀리게 썼다. 또는 뜻이 제시문과 달라졌다.

[uses_target] — 목표 표현을 실제로 썼는지
- 활용형이 달라도(sums up / summed up) 같은 표현을 썼으면 true.
- 뜻이 비슷한 다른 표현으로 바꿔 썼다면 false 다.

[good_point] — 잘한 점
- 학습자 문장에서 실제로 잘된 부분을 한 문장으로 짚는다.
- "다시" 판정이어도 반드시 쓴다. 시도 자체를 칭찬하는 빈말이 아니라,
  문장 안에서 구체적으로 맞은 것을 찾아 쓴다.

[target_note] — 목표 표현에 대한 평가
- 목표 표현을 어떻게 썼는지 한두 문장으로 평가한다.
- 틀렸다면 무엇이 왜 틀렸는지 규칙을 설명한다. 고친 문장만 던지지 않는다.
- 맞았다면 무엇이 맞았는지 짚는다. ("타동사로 목적어를 바로 받았다" 처럼)

[corrected] — 고쳐 쓴 문장
- 고칠 것이 있을 때만 학습자 문장을 최소한으로 손봐서 쓴다.
- 학습자가 쓴 어휘와 구조를 최대한 살린다. 모범 답안으로 갈아치우지 않는다.
- 고칠 것이 없으면 빈 문자열로 둔다.

[other_notes] — 그 밖의 지적
- 목표 표현과 무관한 오류를 **최대 2개까지만** 짧게 적는다. 없으면 빈 배열.
- 뜻이 통하는 사소한 차이는 넣지 않는다. 관사나 구두점은 뜻이 달라질 때만 짚는다.
- 한국어를 그대로 옮긴 직역체가 있으면 그것을 우선해서 짚는다.

{level_guide}"""

USER_PROMPT = """목표 표현: {expression}
표현의 뜻: {meaning}

학습자에게 보여준 한국어 제시문:
{prompt_ko}

가려 둔 모범 답안 (참고용, 유일한 정답이 아니다):
{model_answer}

학습자가 쓴 문장:
{learner_answer}"""

RETRY_NUDGE = (
    "직전 응답이 올바른 JSON이 아니었다. 이번에는 설명이나 코드 펜스 없이 "
    "스키마를 따르는 JSON 객체 하나만 출력하라."
)


def build_messages(
    *,
    expression: str,
    meaning: str,
    prompt_ko: str,
    model_answer: str,
    learner_answer: str,
    level: str = "intermediate",
    retry: bool = False,
) -> list[ChatMessage]:
    system = SYSTEM_PROMPT.format(
        level_guide=LEVEL_GUIDE.get(level, LEVEL_GUIDE["intermediate"])
    )
    if retry:
        system = f"{system}\n\n{RETRY_NUDGE}"
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=USER_PROMPT.format(
                expression=expression,
                meaning=meaning or "(설명 없음)",
                prompt_ko=prompt_ko,
                model_answer=model_answer,
                learner_answer=learner_answer,
            ),
        ),
    ]
