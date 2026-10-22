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
