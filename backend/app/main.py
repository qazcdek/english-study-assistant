from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.errors import AppError, LLMError
from app.providers.llama_server import LlamaServerProvider
from app.routers import account, analyze, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # 분석 기록은 두 모드 모두 DB 에 남긴다. local 은 docker Postgres, cloud 는 Neon.
    from app.db import User, init_engine, session_scope
    from app.deps import LOCAL_USER_ID

    init_engine(settings.database_url)

    if settings.is_cloud:
        # 웹 배포: 로그인과 회원별 Gemini 키로 동작한다.
        # 프로바이더는 요청마다 만들므로 앱 수준에서는 만들지 않는다.
        settings.require_cloud_settings()
        app.state.provider = None
        yield
        return

    # 로컬: 로그인이 없으므로 모든 기록을 매달 사용자 행 하나를 만들어 둔다.
    with session_scope() as db:
        if db.get(User, LOCAL_USER_ID) is None:
            db.add(User(id=LOCAL_USER_ID, google_sub="local", email="local", name="local"))

    # llama-server 프로바이더 하나를 앱 수명 동안 공유한다.
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
    # 히스토리·단어장·연습 기록은 두 모드 모두 쓴다.
    app.include_router(account.router)
    if settings.is_cloud:
        app.include_router(auth.router)

    _mount_frontend(app)
    return app


def _static_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "static"


def _mount_frontend(app: FastAPI) -> None:
    """빌드된 프론트엔드가 옆에 있으면 같은 오리진에서 서빙한다.

    프론트와 API 를 다른 도메인에 두면 세션 쿠키가 cross-site 가 되어
    SameSite=None; Secure 와 CORS 자격 증명 설정을 모두 맞춰야 한다.
    한 오리진에서 서빙하면 그 문제가 통째로 사라진다.
    """
    static_dir = _static_dir()
    index = static_dir / "index.html"
    if not index.is_file():
        return

    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(static_dir / "favicon.svg")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        # /api 밑의 미매칭 경로까지 삼키면 404 가 HTML 로 바뀌어 디버깅이 어려워진다.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(index)


app = create_app()
