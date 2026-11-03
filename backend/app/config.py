from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["local", "cloud"]


class Settings(BaseSettings):
    """환경변수 기반 설정. `.env` 파일이 있으면 자동으로 읽는다.

    `app_mode` 하나로 두 가지 배포 형태를 가른다.

    - local : 내 PC 의 llama-server 에 붙는다. 로그인이 없다.
    - cloud : 웹 배포. Google 로그인 + 회원별 Gemini API 키로 호출한다.

    **분석 기록은 두 모드 모두 DB 에 남긴다.** local 은 docker Postgres(15432),
    cloud 는 Neon 을 가리킨다. 갈리는 것 전체는 09-mode-matrix.md 를 본다.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_mode: Mode = "local"

    # --- 로컬 LLM (llama-server) ---
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_model: str = "local-model"
    llm_api_key: str = ""
    llm_timeout: float = 300.0
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    # **Gemini 의 사고 수준.** `-lite` 가 아닌 flash 는 사고 모델이라, 안 걸면
    # 짧은 답 하나에도 토큰을 수백 개 쓴다. 같은 요청을 재 보니
    # `gemini-3.8-flash` 가 합계 523 → `low` 로 61 토큰이었다 (`M3-T7` 실측).
    # 빈 문자열이면 안 보낸다. `none` 은 lite 가 거부하므로 기본값으로 두지 않는다.
    gemini_reasoning_effort: str = "low"
    llm_enable_thinking: bool | None = False
    llm_json_mode: Literal["json_schema", "json_object", "none"] = "json_schema"

    # --- 공용 뉴스 출처 (cloud) ---
    # 가디언 Content API 키. **비어 있으면 뉴스 고르기가 꺼진다** — 앱은 정상으로
    # 뜨고 "아직 준비된 뉴스가 없습니다" 가 그대로 나온다. 분기를 하나 더 두는
    # 대신 **데이터가 비어 있게** 하는 09 §3.8 의 방식과 같다.
    #
    # 이 키는 서버 것이다. 회원이 등록하는 LLM 키(`provider_keys`)와 달리 출처는
    # 모든 회원에게 하나이므로, 환경변수에 두는 것이 맞는 자리다.
    guardian_api_key: str = ""
    guardian_base_url: str = "https://content.guardianapis.com"
    guardian_timeout: float = 30.0

    # --- Gemini (cloud) ---
    # 회원이 등록한 API 키로 호출하므로 서버에는 키를 두지 않는다.
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_timeout: float = 120.0

    # --- 인증 (cloud) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    # OAuth 콜백이 돌아올 백엔드 주소. 예: https://eng-study.onrender.com
    #
    # **아래 둘은 스킴과 호스트가 같아야 한다.** 콜백이 세션 쿠키를
    # `public_base_url` 의 호스트에 심고, 그 직후 `frontend_base_url` 로 보낸다.
    # 쿠키는 **포트는 무시하지만 호스트 이름은 구분한다** — `127.0.0.1` 에 심은
    # 쿠키는 `localhost` 에서 안 실린다. 그러면 로그인이 **오류 없이** 안 된다:
    # 콜백은 303 으로 잘 돌아오고 화면만 다시 로그인 화면이다.
    # 스킴도 같아야 한다 — `secure` 플래그를 `public_base_url` 에서 끌어오므로
    # (`routers/auth.py`), 백엔드만 https 면 http 프론트에 쿠키가 안 실린다.
    #
    # 전에는 기본값과 `.env.example` 이 `127.0.0.1` 과 `localhost` 로 갈려 있었다 (H-044).
    public_base_url: str = "http://127.0.0.1:8000"
    # 로그인 후 사용자를 돌려보낼 프론트엔드 주소. **위와 같은 호스트.**
    frontend_base_url: str = "http://127.0.0.1:5173"
    session_secret: str = ""
    session_days: int = 30
    # 오류 수집. **비어 있으면 아무것도 보내지 않는다** — 로컬에서 켜질 일이 없어야 한다.
    # 무엇을 지우고 보내는지는 app/observability.py 와 07-web-deployment.md §9.
    sentry_dsn: str = ""
    # 배포본이 어느 커밋인지. Render 가 넣어 주는 값을 그대로 받는다.
    render_git_commit: str = ""
    # 회원 Gemini 키를 암호화하는 Fernet 키 (base64 32바이트)
    encryption_key: str = ""

    # --- 저장소 (두 모드 공통) ---
    # local 은 compose.yaml 이 띄우는 Postgres, cloud 는 Neon 을 가리킨다.
    # 기본 포트(5432)는 이미 깔려 있는 Postgres 와 부딪히므로 15432 를 쓴다.
    database_url: str = "postgresql+psycopg://eng:eng@127.0.0.1:15432/eng_study"

    # --- 입력 제한 ---
    #
    # 모드별로 다르다. 한쪽만 보고 고치면 다른 쪽이 조용히 어긋난다 (09-mode-matrix.md §3.1).
    #   local  넉넉히. 혼자 쓰고 llama-server 한도만 신경 쓰면 된다
    #   cloud  좁게.  회원 각자의 Gemini 한도를 소모한다
    local_max_input_chars: int = 2000
    cloud_max_input_chars: int = 1200

    # --- 사용량 제한 ---
    daily_analysis_limit: int = 60
    daily_practice_limit: int = 200

    # --- HTTP ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


    @property
    def is_cloud(self) -> bool:
        return self.app_mode == "cloud"

    @property
    def max_input_chars(self) -> int:
        """이 모드에서 받는 입력 길이 상한.

        프론트는 이 값을 하드코딩하지 않고 `GET /api/config` 로 받아 쓴다.

        [문서] 09-mode-matrix.md §3.1
        """
        return self.cloud_max_input_chars if self.is_cloud else self.local_max_input_chars

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def require_cloud_settings(self) -> None:
        """cloud 모드에서 반드시 채워져야 하는 값들을 확인한다."""
        missing = [
            name
            for name in ("google_client_id", "google_client_secret", "session_secret", "encryption_key")
            if not getattr(self, name)
        ]
        if missing:
            raise RuntimeError(
                "APP_MODE=cloud 인데 다음 환경변수가 비어 있습니다: "
                + ", ".join(n.upper() for n in missing)
            )
        if len(self.session_secret) < 32:
            raise RuntimeError("SESSION_SECRET 은 32자 이상이어야 합니다.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
