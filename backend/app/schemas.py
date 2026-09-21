"""요청/응답 및 분석 결과 모델.

여기의 `AnalysisResult` 계열 모델은 `app/prompts/analysis.py` 의
`ANALYSIS_JSON_SCHEMA` 와 1:1로 대응한다. 한쪽을 바꾸면 다른 쪽도 바꿔야 한다.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Level = Literal["beginner", "intermediate", "advanced"]

# 입력 길이 상한. frontend/src/components/InputPanel.tsx 의 MAX_CHARS 와 같아야 한다.
#
# 로컬은 내가 혼자 쓰고 llama-server 한도만 신경 쓰면 되므로 넉넉히 둔다.
# 웹 배포(main)는 회원의 Gemini 한도를 소모하므로 800자로 더 좁다.
MAX_INPUT_CHARS = 2000

ExpressionType = Literal[
    "고급 어휘",
    "관용구",
    "Phrasal Verb",
    "연어(Collocation)",
    "문법 포인트",
    "구어 표현",
    "전문 용어",
]
Formality = Literal["매우 격식", "격식", "중립", "비격식", "속어에 가까움"]
Style = Literal["문어체", "구어체", "혼합"]


# --------------------------------------------------------------------------- 요청


class AnalyzeRequest(BaseModel):
    text: str = Field(
        min_length=1, max_length=MAX_INPUT_CHARS, description="분석할 영어 문장 또는 문단"
    )
    level: Level = "intermediate"

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("분석할 텍스트가 비어 있습니다.")
        return stripped


# --------------------------------------------------------------------------- 분석 결과


class Expression(BaseModel):
    expression: str = Field(description="원문에 등장한 영어 표현 그대로")
    type: ExpressionType
    meaning: str = Field(description="한국어 대역어 한두 개")
    nuance: str = Field(
        default="",
        description="어떤 상황에서 쓰는지·뉘앙스. 초급에서는 쓰지 않는다",
    )
    example: str | None = Field(default=None, description="다른 맥락의 예문. 확실하지 않으면 생략")
    example_ko: str | None = Field(default=None, description="example 의 한국어 뜻. 작문 연습의 제시문")


class StructureNote(BaseModel):
    """구문 해설.

    한 필드에 몰아넣으면 모델이 구조 이름만 대고 끝내거나 문법 일반론으로 흘렀다.
    빠뜨릴 수 없도록 조각을 나눈다.
    """

    fragment: str = Field(description="해설 대상이 되는 원문 조각")
    name: str = Field(description="이 구조의 이름. 표준 문법 용어")
    role: str = Field(description="이 문장에서 그 구조가 하는 일. 문법 일반론이 아님")
    rewrite: str = Field(default="", description="쉬운 말로 바꿔 쓴 등가 표현. 어려우면 빈 문자열")
    pitfall: str = Field(default="", description="한국어 화자가 놓치기 쉬운 지점")


class Overview(BaseModel):
    """이 글이 어떤 분야에서 어떤 톤으로 쓰였고, 무엇을 챙겨 가야 하는지."""

    domain: str = Field(description="어떤 분야의 글인지 (예: 경제·금융 시사 논평)")
    tone: str = Field(description="글쓴이의 태도·어조를 짧은 구로 (예: 냉소가 섞인 분석적 어조)")
    formality: Formality
    style: Style
    key_expressions: list[str] = Field(
        default_factory=list,
        description="expressions 중 특히 챙길 표현. expression 값과 정확히 같아야 한다",
    )
    comment: str = Field(description="왜 그 표현들이 중요한지, 어디에 쓰면 되는지 두세 문장")


class AnalysisResult(BaseModel):
    """파트별로 채워지는 결과. 실패한 파트는 비어 있을 수 있다."""

    source_text: str = ""
    translation: str = ""
    expressions: list[Expression] = Field(default_factory=list)
    structures: list[StructureNote] = Field(default_factory=list)
    overview: Overview | None = None


# --------------------------------------------------------------------------- 파트 응답
# LLM 은 파트마다 {"<field>": ...} 한 겹으로 감싼 객체를 돌려준다.


class TranslationPart(BaseModel):
    translation: str


class ExpressionsPart(BaseModel):
    expressions: list[Expression] = Field(default_factory=list)


class StructuresPart(BaseModel):
    structures: list[StructureNote] = Field(default_factory=list)


class OverviewPart(BaseModel):
    overview: Overview


# --------------------------------------------------------------------------- 응답


class MarkdownSections(BaseModel):
    translation: str = ""
    expressions: str = ""
    structures: str = ""
    overview: str = ""
    full: str = ""


class AnalyzeMeta(BaseModel):
    model: str
    elapsed_ms: int
    retried_parts: list[str] = Field(default_factory=list)
    failed_parts: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- 스트리밍 이벤트


class PartEvent(BaseModel):
    type: Literal["part"] = "part"
    field: str
    title: str
    index: int
    total: int
    data: dict
    markdown: str
    elapsed_ms: int
    retried: bool = False


class PartErrorEvent(BaseModel):
    type: Literal["part_error"] = "part_error"
    field: str
    title: str
    index: int
    total: int
    code: str
    message: str
    detail: str | None = None


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    result: AnalysisResult
    markdown: MarkdownSections
    meta: AnalyzeMeta


class AnalyzeResponse(BaseModel):
    result: AnalysisResult
    markdown: MarkdownSections
    meta: AnalyzeMeta


class LLMHealth(BaseModel):
    reachable: bool
    base_url: str
    models: list[str] = Field(default_factory=list)
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    llm: LLMHealth


# --------------------------------------------------------------------------- 작문 연습

Verdict = Literal["정확함", "통함", "다시"]


class PracticeRequest(BaseModel):
    """예문을 가린 채 학습자가 쓴 영어 문장을 채점한다."""

    expression: str = Field(min_length=1, max_length=100, description="연습 대상 표현")
    meaning: str = Field(default="", max_length=1000, description="표 풀이의 의미 설명")
    prompt_ko: str = Field(min_length=1, max_length=500, description="학습자에게 보여준 한국어 제시문")
    model_answer: str = Field(min_length=1, max_length=500, description="가려 둔 모범 답안")
    learner_answer: str = Field(min_length=1, max_length=500, description="학습자가 쓴 영어 문장")
    level: Level = "intermediate"

    @field_validator("learner_answer")
    @classmethod
    def not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("작성한 문장이 비어 있습니다.")
        return stripped


class PracticeResult(BaseModel):
    verdict: Verdict
    uses_target: bool = Field(description="목표 표현을 실제로 썼는지")
    good_point: str = Field(description="잘한 점 한 문장")
    target_note: str = Field(description="목표 표현 사용에 대한 평가와 설명")
    corrected: str = Field(default="", description="고쳐 쓴 문장. 고칠 것이 없으면 빈 문자열")
    other_notes: list[str] = Field(default_factory=list, description="부차적인 지적. 최대 2개")


class PracticeResponse(BaseModel):
    result: PracticeResult
    model_answer: str
    meta: AnalyzeMeta


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
