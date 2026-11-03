"""요청/응답 및 분석 결과 모델.

여기의 `AnalysisResult` 계열 모델은 `app/prompts/analysis.py` 의
`ANALYSIS_JSON_SCHEMA` 와 1:1로 대응한다. 한쪽을 바꾸면 다른 쪽도 바꿔야 한다.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Level = Literal["beginner", "intermediate", "advanced"]

# 어떤 모드에서도 넘을 수 없는 절대 상한.
#
# 실제로 적용되는 값은 모드마다 다르다(`Settings.max_input_chars`). 여기는 그보다 넓게 두고,
# 모드별 제한은 라우터에서 건다. 이 값을 모드별 값으로 착각하지 말 것 — 09-mode-matrix.md §3.1.
ABSOLUTE_MAX_INPUT_CHARS = 2000

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
        min_length=1, max_length=ABSOLUTE_MAX_INPUT_CHARS, description="분석할 영어 문장 또는 문단"
    )

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("분석할 텍스트가 비어 있습니다.")
        return stripped


# --------------------------------------------------------------------------- 분석 결과


class ExamplePair(BaseModel):
    """예문 한 쌍 — 영어와 그 한국어 뜻."""

    en: str = Field(default="", description="그 난이도의 예문")
    ko: str = Field(default="", description="그 문장의 한국어 뜻. 작문 연습의 제시문")


class Examples(BaseModel):
    """난이도별 예문 셋 (M16).

    **난이도가 분석에서 여기로 옮겨 왔다.** 분석의 깊이는 정도부사로밖에 적을 수
    없어 판정이 안 됐는데(`08 §1`), 예문 난이도는 단어 수와 절 개수로 적힌다.

    셋 다 기본값이 있다 — **낡은 기록은 중급 하나만 들고 있다** (`records.upgrade`
    가 옛 `example`/`example_ko` 를 그 자리로 옮긴다).
    """

    beginner: ExamplePair = Field(default_factory=ExamplePair)
    intermediate: ExamplePair = Field(default_factory=ExamplePair)
    advanced: ExamplePair = Field(default_factory=ExamplePair)


class Expression(BaseModel):
    expression: str = Field(description="원문에 등장한 영어 표현 그대로")
    type: ExpressionType
    meaning: str = Field(description="한국어 대역어 한두 개")
    nuance: str = Field(default="", description="어떤 상황에서 쓰는지·뉘앙스")
    examples: Examples = Field(default_factory=Examples)


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
    # 채점은 이 둘을 쓰지 않는다. **연습한 표현을 나의 표현에 올릴 때** 쓴다 —
    # 채점과 등록을 두 번 호출하게 하면 뒤쪽이 실패해 입구 없는 기록이 남는다.
    type: str = Field(default="", max_length=40, description="표현 유형. 나의 표현에 그대로 올린다")
    source_text: str = Field(default="", max_length=2000, description="이 표현이 나온 원문")
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


# --------------------------------------------------------------------------- 앱 설정


class ProviderOption(BaseModel):
    """화면이 모델 선택을 그리는 데 필요한 것.

    **프론트가 목록을 들고 있지 않다.** 고를 수 있는 범위가 모드로 갈리므로
    (09 §3.2), 서버가 정한 것을 그대로 그린다 — 프론트에 적으면 모드가 바뀔 때 어긋난다.
    """

    id: str
    label: str
    models: list[str]
    needs_key: bool
    key_url: str = ""


class AppConfigResponse(BaseModel):
    """프론트가 어떤 화면을 그릴지 정하는 데 필요한 최소 정보."""

    mode: Literal["local", "cloud"]
    requires_login: bool
    # **아직 안 고른 회원이 돌리게 되는 모델.** 지금 쓰는 모델이 아니다 —
    # 고른 뒤에는 `GET /api/account/settings` 의 `active_model` 이 답한다.
    # 이름이 `model` 이었을 때 **"지금 쓰는 것" 으로 읽혔고**, 그래서 설정값
    # 사본을 보고하는 것이 오래 안 들켰다 (H-042).
    default_model: str
    daily_analysis_limit: int = 0
    daily_practice_limit: int = 0
    api_key_issue_url: str = ""
    max_input_chars: int = ABSOLUTE_MAX_INPUT_CHARS
    # 이 모드에서 고를 수 있는 제공자. 아직 안 되는 것은 **담기지 않는다**
    # (고를 수 있는데 안 되는 것은 목록에 없는 것보다 나쁘다).
    providers: list[ProviderOption] = []
    default_provider: str = ""


# --------------------------------------------------------------------------- 계정 (cloud)


class AccountResponse(BaseModel):
    email: str
    name: str
    picture: str
    has_consented: bool
    # **지금 고른 제공자의** 키가 있나. 키를 제공자마다 따로 두므로 회원 단위 사실이
    # 아니다 — 다른 제공자 키가 있어도 지금 쓸 것이 없으면 호출할 수 없다 (M12-T2).
    has_api_key: bool
    api_key_hint: str = ""
    # 제공자 → 끝 네 자리. **평문은 서버 밖으로 나가지 않는다.**
    keys: dict[str, str] = {}
    # 회원 전역 설정. 바꿔 저장하면 그 뒤의 모든 작업이 이것으로 간다.
    active_provider: str = ""
    active_model: str = ""
    #: 운영자인가. **화면이 지난 뉴스 목록을 띄울지 가린다** (M13-T13).
    #: 권한 자체는 서버가 본다 — 이 값은 **보여줄지 말지**에만 쓴다.
    is_operator: bool = False


class ConsentRequest(BaseModel):
    agreed: bool


class AccountSettings(BaseModel):
    """지금 어느 제공자·모델로 일하나, 어디에 키가 있나.

    **두 모드가 같은 모양을 쓴다.** 로컬에도 제공자 선택이 필요하므로(local 은
    llama-server 와 cloud LLM 전부를 고를 수 있다) 이 엔드포인트는 `account` 라우터에
    있고, cloud 전용인 `auth` 에 두지 않는다 (09 §3.2).
    """

    active_provider: str
    active_model: str
    # 제공자 → 끝 네 자리. **평문은 서버 밖으로 나가지 않는다.**
    keys: dict[str, str] = {}
    # 지금 고른 제공자로 호출할 수 있나 (키가 필요 없는 제공자는 항상 참).
    ready: bool = False


class ActiveModelRequest(BaseModel):
    """쓸 제공자와 모델을 고른다. **저장하는 순간부터 모든 작업이 그것으로 간다.**"""

    provider: str
    model: str = ""


class ApiKeyRequest(BaseModel):
    api_key: str = Field(min_length=10, max_length=200)
    # 어느 제공자의 키인가. 비우면 지금 고른 제공자로 본다.
    provider: str = ""

    @field_validator("api_key")
    @classmethod
    def strip_key(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("API 키가 비어 있습니다.")
        return stripped


class UsageResponse(BaseModel):
    day: str
    analyses: int
    practices: int
    analysis_limit: int
    practice_limit: int


class DeletionSummary(BaseModel):
    """무엇이 몇 건 지워졌는지. 화면이 "N건을 지웠습니다" 로 쓴다."""

    analyses: int
    practices: int
    vocabulary: int
    usage_counters: int


# --------------------------------------------------------------------------- 저장 데이터


class HistoryItem(BaseModel):
    """저장된 분석 하나. **난이도 칸이 없다** (`M16`) — 분석은 한 가지로 돈다."""

    id: int
    source_text: str
    created_at: str
    failed_parts: list[str] = Field(default_factory=list)


class TidySummary(BaseModel):
    """정리 결과. **몇 건이 사라졌는지**를 돌려준다.

    화면이 미리 셌더라도 실제 건수는 서버만 안다 — 그 사이에 다른 기기에서
    분석했을 수 있다.
    """

    removed: int


class HistoryDetail(HistoryItem):
    result: AnalysisResult
    markdown: MarkdownSections


class VocabularyCreate(BaseModel):
    """나의 표현에 담는다.

    **예문은 한 쌍만 든다.** 표에서 담을 때 보고 있던 난이도의 것이다 — 나의 표현은
    "내가 고른 문장" 이므로 셋을 다 끌고 오면 무엇을 고른 것인지 사라진다 (`M16`).
    """

    expression: str = Field(min_length=1, max_length=200)
    type: str = ""
    meaning: str = ""
    example: str = ""
    example_ko: str = ""
    source_text: str = ""


class VocabularyItemOut(VocabularyCreate):
    id: int
    created_at: str
    # 제외하면 이만큼의 연습 기록이 함께 사라진다. 화면이 이 값을 보고 한 번 더 묻는다.
    practice_count: int = 0


class VocabularyRemoval(BaseModel):
    """제외한 결과. **연습 기록이 몇 건 함께 사라졌는지**를 돌려준다.

    화면이 미리 물어봤더라도 실제로 몇 건이 사라졌는지는 서버만 안다.
    그 사이에 다른 기기에서 연습했을 수 있다.
    """

    ok: bool = True
    expression: str
    practices_deleted: int


class PracticeHistoryItem(BaseModel):
    id: int
    expression: str
    prompt_ko: str
    model_answer: str
    learner_answer: str
    verdict: Verdict
    uses_target: bool
    feedback: PracticeResult
    created_at: str


# --------------------------------------------------------------------------- 공용 뉴스


class ParagraphOut(BaseModel):
    """뉴스의 문단 하나. **본문만** 담는다 — 분석은 펼칠 때 따로 가져온다."""

    ordinal: int
    text: str
    #: 미리 분석이 있나. 미리 분석이 중간에 멈추면 뒤쪽 문단이 `false` 로 남는다.
    prepared: bool


class ArticleOut(BaseModel):
    """지금 보여줄 뉴스 한 편.

    **`picked_for` 를 숨기지 않는다.** 오늘 것이 아직 없으면 어제 것을 보여주는
    것이 규정이므로(09 §3.8), 며칠 뉴스인지는 회원이 보고 알아야 한다.

    **`byline` 과 `url` 은 선택이 아니다.** 출처 약관이 기자 크레딧과 원문 백링크를
    요구하므로(M13-T10) 화면이 둘 다 적는다.

    **난이도 칸이 없다** (`M16`) — 분석이 한 가지로 도므로 "어느 난이도로 준비됐나" 가
    사라졌다. 예문 난이도는 회원이 연습할 때 고른다.
    """

    id: int
    source: str
    url: str
    title: str
    byline: str
    section: str
    published_at: str
    picked_for: str
    paragraphs: list[ParagraphOut]


class ArticleListResponse(BaseModel):
    """지난 뉴스 목록 — **운영자만 본다** (M13-T13).

    `ArticleOut` 을 그대로 담는다. 목록용으로 줄인 모양을 따로 두면 화면이 두 가지를
    그려야 하고, 하나를 고쳐 열 때 또 받아 와야 한다. 문단 본문까지 들어 있지만
    분석은 빠져 있어(`M13-T6` 이 가른 자리) 한 편이 수 KB 다.
    """

    articles: list[ArticleOut] = []


class DailyArticleResponse(BaseModel):
    """뉴스가 없을 수 있다. **그것은 오류가 아니라 정상 상태다** — 첫 배포 직후와
    고르기가 실패하고 있는 동안이 그렇다. 404 로 두면 화면이 정상 상태에 오류 옷을
    입힌다.
    """

    article: ArticleOut | None = None


class ParagraphAnalysisOut(BaseModel):
    """문단 하나의 미리 분석.

    **`HistoryDetail` 과 같은 칸을 든다** — 같은 분석기가 만들고 같은 화면이 읽는다
    (`db/models.py` 의 `ParagraphAnalysis`). 다른 것은 주인이 없다는 것뿐이다.
    문단 본문은 `result.source_text` 에 이미 들어 있으므로 따로 담지 않는다.
    """

    ordinal: int
    result: AnalysisResult
    markdown: MarkdownSections
    failed_parts: list[str] = Field(default_factory=list)
    #: 어느 모델이 만들었나. 회원 기록과 달리 **운영자 키로** 돌았다.
    model: str = ""


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
