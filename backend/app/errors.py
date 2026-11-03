class LLMError(Exception):
    """LLM 호출 계층에서 발생한 오류의 공통 조상."""

    code = "llm_error"
    http_status = 502
    message = "LLM 호출 중 오류가 발생했습니다."

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or self.message)
        self.detail = detail


class LLMUnavailableError(LLMError):
    code = "llm_unavailable"
    http_status = 503
    message = "로컬 LLM 서버에 연결할 수 없습니다. llama-server 가 실행 중인지 확인해 주세요."


class LLMTimeoutError(LLMError):
    code = "llm_timeout"
    http_status = 504
    message = "LLM 응답 시간이 초과되었습니다. 입력을 줄이거나 다시 시도해 주세요."


class LLMBadOutputError(LLMError):
    code = "llm_bad_output"
    http_status = 502
    message = "LLM이 형식에 맞는 결과를 내지 못했습니다. 다시 시도해 주세요."


class LLMTruncatedError(LLMError):
    code = "llm_truncated"
    http_status = 502
    message = (
        "LLM 응답이 max_tokens 한도에서 잘렸습니다. "
        "LLM_MAX_TOKENS 를 늘리거나 LLM_ENABLE_THINKING 을 끄고 다시 시도해 주세요."
    )


class AppError(Exception):
    """LLM 호출 밖에서 발생하는, 사용자에게 그대로 보여줄 오류.

    **넘긴 문구는 `message` 가 된다.** 전에는 `detail` 로 들어갔는데, 화면은 `message`
    를 크게 보여주고 `detail` 은 작은 고정폭으로 덧붙인다 — 그래서
    `AppError("먼저 이용 동의를 해 주세요.")` 같은 호출이 **"요청을 처리할 수
    없습니다." 아래 작은 글씨로** 나왔다. 하위 클래스는 자기 `message` 를 그대로 쓴다.
    """

    code = "app_error"
    http_status = 400
    message = "요청을 처리할 수 없습니다."

    def __init__(self, message: str = "", *, detail: str = "") -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message
        self.detail = detail


class NotFoundError(AppError):
    """그 기록이 없다, **또는 내 것이 아니다.**

    두 경우를 구별하지 않는다. 다르게 답하면 id 를 훑어 남의 기록이 존재하는지
    알아낼 수 있다 — 내용을 못 봐도 그건 누출이다 (03-api-spec.md, 14-data-layer.md §3.1).
    """

    code = "not_found"
    http_status = 404
    message = "기록을 찾을 수 없습니다."


class AuthRequiredError(AppError):
    code = "auth_required"
    http_status = 401
    message = "로그인이 필요합니다."


class ConsentRequiredError(AppError):
    code = "consent_required"
    http_status = 403
    message = "서비스 이용 동의가 필요합니다."


class ApiKeyRequiredError(AppError):
    code = "api_key_required"
    http_status = 403
    message = "Gemini API 키를 먼저 등록해 주세요. 분석은 회원님 키로 호출됩니다."


class UsageLimitError(AppError):
    code = "usage_limit"
    http_status = 429
    message = "오늘 사용 한도를 모두 썼습니다. 내일 다시 이용해 주세요."


class ForbiddenError(AppError):
    """로그인은 했지만 **그 일을 할 자격이 없다** (M13-T13).

    401 이 아니다 — 다시 로그인해도 달라지지 않는다. 404 로 숨기지도 않는다:
    지난 뉴스 목록은 **비밀이 아니라 운영자용 도구**이고, 404 로 두면 경로가
    썩었는지 자격이 없는지 운영자 자신도 구별하지 못한다.
    """

    code = "forbidden"
    http_status = 403
    message = "이 작업을 할 권한이 없습니다."


class OperatorKeyRequiredError(AppError):
    """공용 뉴스를 만들 수 없다 — 운영자가 없거나 그 키가 없다 (M13-T5).

    `ApiKeyRequiredError` 와 **다르다.** 그쪽은 회원이 자기 키를 등록하면 풀리지만,
    이것은 **회원이 할 수 있는 일이 없다.** 그래서 문구에 "등록해 주세요" 를 넣지
    않고, 4xx 가 아니라 **503** 을 쓴다 — 서버 쪽이 아직 준비되지 않은 것이다.
    """

    code = "operator_key_required"
    http_status = 503
    message = "읽을 글을 준비하는 중입니다. 잠시 후 다시 시도해 주세요."


class ArticleBodyError(AppError):
    """기사 본문이 **문단으로 쪼개지지 않았다** (M13-T8).

    `<p>` 가 없거나 전부 50자 미만일 때다 — 사진 기사나 라이브블로그가 그렇다
    (`services/paragraphs.py` 의 하한).

    **그냥 넣고 넘어가면 안 된다.** 문단이 0개인 기사를 앉히면 화면에 빈 뉴스이
    뜨고, 더 나쁘게는 **미리 분석이 영원히 "다 됐다" 로 읽힌다** — 돌 문단이
    없으므로 `prepare.article()` 이 아무 일도 하지 않고 성공한다. 고르는 쪽
    (`M13-T4`)은 이것을 보고 다음 후보로 넘어가야 한다.
    """

    code = "article_body"
    http_status = 502
    message = "기사 본문을 문단으로 쪼갤 수 없습니다."


class ArticleLengthError(ArticleBodyError):
    """문단은 쪼개졌는데 **약관 안에 드는 토막이 없다** (M13-T9).

    문단 **하나하나가** 상한을 넘을 때다 (`paragraphs.WORD_LIMIT`). 쪼개기는
    성공했으므로 위와 원인이 다르지만, **해야 할 일은 같다** — 이 기사를 버리고
    다음 인기 기사로 넘어간다.

    그래서 `ArticleBodyError` 를 물려받는다. 고르는 쪽(`M13-T4`)이 `except
    ArticleBodyError` 하나만 적어도 **이 경우를 빼먹을 수 없다.** 둘을 나란한
    형제로 두면 둘째를 잊은 채 통과하는 길이 열린다.
    """

    code = "article_length"
    message = "약관이 허용하는 분량 안에 드는 문단이 없습니다."


class ArticleCreditError(ArticleBodyError):
    """기자 크레딧이 없다 (M13-T10).

    출처 약관이 **기자 이름과 원문 출처를 명확히 적으라고** 요구하므로, 크레딧이
    빈 기사는 보여줄 수 없다. 빈 칸으로 앉혀 두면 화면이 **크레딧 없이 번역을
    내보내는 쪽**으로 조용히 기운다.

    `ArticleLengthError` 와 같은 이유로 `ArticleBodyError` 를 물려받는다 —
    원인은 셋이 다르지만 할 일은 하나다: 이 기사를 버리고 다음 후보로.
    """

    code = "article_credit"
    message = "기사에 기자 크레딧이 없습니다."


class ArticleSourceError(AppError):
    """출처에서 후보를 가져오지 못했다 (M13-T4).

    키가 비었거나, HTTP 가 실패했거나, 응답에 쓸 기사가 없을 때다. **위 셋과
    형제가 아니다** — `ArticleBodyError` 는 "이 기사를 버리고 다음 후보로" 이고,
    이것은 **후보 목록 자체가 없다**는 뜻이라 넘어갈 다음이 없다. 고르는 쪽이
    이것을 보고 쿨다운을 적는다.

    `detail` 에 **키를 담지 않는다.** `httpx` 의 오류 문구에는 요청 URL 이 들어가고
    거기에 `api-key` 가 붙어 있다 — 그대로 적으면 DB 와 화면에 키가 남는다.
    """

    code = "article_source"
    http_status = 502
    message = "뉴스 출처에서 기사를 가져오지 못했습니다."
