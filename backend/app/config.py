from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["local", "cloud"]


class Settings(BaseSettings):
    """환경변수 기반 설정. `.env` 파일이 있으면 자동으로 읽는다.

    `app_mode` 하나로 두 가지 배포 형태를 가른다.

    - local : 내 PC 의 llama-server 에 붙는다. 로그인도 DB 도 없다.
    - cloud : 웹 배포. Google 로그인 + 회원별 Gemini API 키로 호출한다.
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
    llm_enable_thinking: bool | None = False
    llm_json_mode: Literal["json_schema", "json_object", "none"] = "json_schema"

    # --- Gemini (cloud) ---
    # 회원이 등록한 API 키로 호출하므로 서버에는 키를 두지 않는다.
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout: float = 120.0

    # --- 인증 (cloud) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    # OAuth 콜백이 돌아올 백엔드 주소. 예: https://eng-study.onrender.com
    public_base_url: str = "http://127.0.0.1:8000"
    # 로그인 후 사용자를 돌려보낼 프론트엔드 주소
    frontend_base_url: str = "http://localhost:5173"
    session_secret: str = ""
    session_days: int = 30
    # 회원 Gemini 키를 암호화하는 Fernet 키 (base64 32바이트)
    encryption_key: str = ""

    # --- 저장소 (cloud) ---
    database_url: str = "sqlite+pysqlite:///./eng_study.db"

    # --- 사용량 제한 ---
    daily_analysis_limit: int = 60
    daily_practice_limit: int = 200

    # --- HTTP ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- 입력 제한 ---
    max_input_chars: int = 4000

    @property
    def is_cloud(self) -> bool:
        return self.app_mode == "cloud"

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
