from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import LLMError
from app.providers.llama_server import LlamaServerProvider
from app.routers import analyze


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
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

    app.include_router(analyze.router)
    return app


app = create_app()
