from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 설정. `.env` 파일이 있으면 자동으로 읽는다."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM (llama-server) ---
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_model: str = "local-model"
    llm_api_key: str = ""
    llm_timeout: float = 300.0
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    # reasoning 모델(Qwen3 등)의 사고 과정을 켤지. 켜면 max_tokens 를 넉넉히 잡아야 한다.
    llm_enable_thinking: bool | None = False
    llm_json_mode: Literal["json_schema", "json_object", "none"] = "json_schema"

    # --- HTTP ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
