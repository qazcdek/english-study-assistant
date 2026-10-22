"""오류 수집(Sentry). **무엇을 보내지 않는지가 이 파일의 본체다.**

Sentry 는 외부 서비스다. 오류 하나를 보낼 때 요청 맥락이 함께 가는데, 이 앱의 요청에는
**회원이 분석한 글 전체**(개인적인 글일 수 있다)와 **세션 쿠키**가 들어 있다.
회원 Gemini 키는 암호화해 보관하지만, 키를 등록하는 요청의 본문에는 **평문으로** 있다.

기본 설정대로 붙이면 그것들이 나간다. 그래서 `scrub` 이 먼저고 `init` 이 그다음이다.

**기대를 정확히 둔다.** 여기가 잡는 것은 *예외가 났는데 아무도 모르는 상태*다.
조용히 나빠지는 것 — 예문이 비거나 입구가 사라지는 종류(H-019 · H-021) — 은 예외가
아니므로 못 잡는다. 그건 검사와 실측의 몫이다.
"""

from typing import Any

from app.config import Settings

# 요청에서 통째로 지우는 칸. 본문에 평문 키와 회원의 글이 들어 있다.
DROPPED_REQUEST_KEYS = ("data", "cookies", "env")
# 남기는 헤더 밖의 모든 헤더를 지운다. **허용 목록이다** —
# 금지 목록으로 두면 새 헤더가 생길 때마다 조용히 새어 나간다.
KEPT_HEADERS = ("Content-Type", "Content-Length", "Accept", "User-Agent")
# 이 낱말이 이름에 들어간 값은 어디에 있든 지운다.
SECRET_HINTS = ("key", "secret", "token", "password", "authorization", "cookie")
REDACTED = "[지움]"


def _scrub_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """이름이 비밀값을 시사하는 칸을 지운다. 중첩도 따라 내려간다."""
    cleaned: dict[str, Any] = {}
    for name, value in data.items():
        if any(hint in name.lower() for hint in SECRET_HINTS):
            cleaned[name] = REDACTED
        elif isinstance(value, dict):
            cleaned[name] = _scrub_mapping(value)
        else:
            cleaned[name] = value
    return cleaned


def scrub(event: dict[str, Any], _hint: object = None) -> dict[str, Any]:
    """보내기 직전에 거른다. `before_send` 로 꽂는다.

    지우는 것은 셋이다 —

    1. **요청 본문**(`data`). 분석 요청에는 회원이 넣은 글 전체가, 키 등록 요청에는
       평문 Gemini 키가 있다. 쓸모보다 위험이 크므로 통째로 지운다.
    2. **쿠키와 환경**. 세션 쿠키 하나로 그 회원을 가장할 수 있다.
    3. **허용 목록 밖의 헤더**, 그리고 이름이 비밀값을 시사하는 모든 칸.

    스택 트레이스와 예외 메시지, 경로와 상태 코드는 남긴다. 그게 없으면 보낼 이유가 없다.
    """
    request = event.get("request")
    if isinstance(request, dict):
        for key in DROPPED_REQUEST_KEYS:
            request.pop(key, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                name: value
                for name, value in headers.items()
                if name.lower() in {k.lower() for k in KEPT_HEADERS}
            }

    # **스택 프레임의 지역 변수를 통째로 뺀다.** 여기가 진짜 누출 지점이었다 —
    # 실제 이벤트를 받아 보니 요청 칸은 비어 있었고, 비밀값이 전부 이쪽에 있었다:
    #   exception.values[0].stacktrace.frames[16].vars.body.api_key   ← 평문 키
    #   exception.values[0].stacktrace.frames[16].vars.body.text      ← 회원의 글
    #   exception.values[0].stacktrace.frames[0].vars.scope.headers[7] ← 세션 쿠키
    # **이름으로는 못 막는다** — `body.text` 는 비밀처럼 생기지 않았고, 헤더는 이름 없는
    # 쌍의 목록으로 들어온다. 그래서 구조로 막는다. 디버깅에서 지역 변수를 잃지만,
    # 여기 흐르는 것이 회원의 글과 평문 키이므로 그 교환은 분명하다.
    for group in ("exception", "threads"):
        for value in (event.get(group) or {}).get("values") or []:
            for frame in (value.get("stacktrace") or {}).get("frames") or []:
                frame.pop("vars", None)

    extra = event.get("extra")
    if isinstance(extra, dict):
        event["extra"] = _scrub_mapping(extra)

    # 회원을 식별하는 칸. id 는 남겨 두면 "몇 명에게 났는지" 를 셀 수 있어 쓸모가 있다.
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user.get("id")} if user.get("id") is not None else {}

    return event


def init_sentry(settings: Settings) -> bool:
    """DSN 이 있을 때만 켠다. 켰으면 True.

    **로컬에서는 켜지지 않는다.** `.env` 에 DSN 이 없고, 있더라도 cloud 가 아니면
    켜지 않는다 — 내 PC 에서 난 오류를 외부로 보낼 이유가 없다 (09 §3.7).
    """
    if not settings.sentry_dsn or not settings.is_cloud:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        # 이름·이메일·IP 를 자동으로 붙이지 않는다. 기본값이지만 **명시한다** —
        # 기본값에 기대면 SDK 가 기본값을 바꿀 때 조용히 새어 나간다.
        send_default_pii=False,
        before_send=scrub,
        # 지역 변수를 애초에 수집하지 않는다. `scrub` 이 한 번 더 지우지만,
        # **두 겹으로 막는다** — 한 겹은 옵션이고 한 겹은 구조다.
        include_local_variables=False,
        # 성능 추적은 끈다. 요청마다 표본을 보내면 비용이 들고, 지금 알고 싶은 것은
        # "터졌는지" 하나다.
        traces_sample_rate=0.0,
        release=settings.render_git_commit or None,
        environment="cloud",
    )
    return True
