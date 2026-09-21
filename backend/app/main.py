from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import AppError, LLMError
from app.providers.llama_server import LlamaServerProvider
from app.routers import account, analyze, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    if settings.is_cloud:
        # 웹 배포: 로그인과 회원별 Gemini 키로 동작한다.
        # 프로바이더는 요청마다 만들므로 여기서는 DB 만 준비한다.
        settings.require_cloud_settings()
        from app.db import init_engine

        init_engine(settings.database_url)
        app.state.provider = None
        yield
        return

    # 로컬: llama-server 프로바이더 하나를 앱 수명 동안 공유한다.
    app.state.provider = LlamaServerProvider(
        settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        json_mode=settings.llm_json_mode,
        enable_thinking=settings.llm_enable_thinking,
    )
    try:
        yield
    finally:
        await app.state.provider.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="English Study Assistant",
        description="영어 문장을 번역 · 표현 · 구조 · 총평으로 정리하는 API",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        # cloud 모드는 세션 쿠키를 주고받아야 한다.
        allow_credentials=settings.is_cloud,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(LLMError)
    async def llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {"code": exc.code, "message": exc.message, "detail": exc.detail or None}
            },
        )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {"code": exc.code, "message": exc.message, "detail": exc.detail or None}
            },
        )

    app.include_router(analyze.router)
    if settings.is_cloud:
        app.include_router(auth.router)
        app.include_router(account.router)

    return app


app = create_app()
