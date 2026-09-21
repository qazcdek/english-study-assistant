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
