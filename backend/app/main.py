from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import User, init_engine, session_scope
from app.deps import LOCAL_USER_ID
from app.errors import AppError, LLMError
from app.providers.llama_server import LlamaServerProvider
from app.routers import analyze, history


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # 분석 기록을 Postgres 에 남긴다. compose.yaml 이 띄우는 컨테이너를 쓴다.
    init_engine(settings.database_url)
    with session_scope() as db:
        if db.get(User, LOCAL_USER_ID) is None:
            db.add(User(id=LOCAL_USER_ID, name="local"))
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
        description="로컬 LLM(llama-server)으로 영어 문장을 분석하는 API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
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
    app.include_router(history.router)
    return app


app = create_app()
