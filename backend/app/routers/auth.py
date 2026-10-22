"""Google 로그인과 계정 설정."""

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.google import GoogleOAuth, OAuthError
from app.auth.session import COOKIE_NAME, issue_token
from app.config import get_settings
from app.db import User
from app.db.models import utcnow
from app.deps import CipherDep, DbDep, SettingsDep, UserDep
from app.errors import AppError
from app.providers import registry
from app.providers.gemini import verify_api_key
from app.schemas import (
    AccountResponse,
    ActiveModelRequest,
    ApiKeyRequest,
    ConsentRequest,
    DeletionSummary,
)
from app.services import account, keys

router = APIRouter(prefix="/api/auth", tags=["auth"])

CALLBACK_PATH = "/api/auth/google/callback"


def _oauth(settings) -> GoogleOAuth:
    settings.require_cloud_settings()
    return GoogleOAuth(
        settings.google_client_id,
        settings.google_client_secret,
        f"{settings.public_base_url.rstrip('/')}{CALLBACK_PATH}",
        settings.session_secret,
    )


def _account(user: User, db: Session) -> AccountResponse:
    """화면이 그릴 수 있을 만큼. **평문 키는 담지 않는다.**"""
    settings = get_settings()
    choice = keys.resolve(user, settings.app_mode)
    held = keys.providers_with_keys(db, user.id)
    return AccountResponse(
        email=user.email,
        name=user.name,
        picture=user.picture,
        has_consented=user.has_consented,
        # **지금 고른 제공자의** 키가 있나. 회원 단위 사실이 아니다 (M12-T2).
        has_api_key=keys.has_key(db, user, choice),
        api_key_hint=held.get(choice.provider.id, ""),
        keys=held,
        active_provider=choice.provider.id,
        active_model=choice.model,
    )


@router.get("/google/start")
def google_start(settings: SettingsDep, next: str = Query(default="/")) -> RedirectResponse:
    return RedirectResponse(_oauth(settings).authorization_url(next), status_code=307)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    settings: SettingsDep,
    db: DbDep,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> RedirectResponse:
    frontend = settings.frontend_base_url.rstrip("/")
    oauth = _oauth(settings)

    if error or not code:
        return RedirectResponse(f"{frontend}/?login_error={error or 'no_code'}", status_code=303)

    try:
        next_path = oauth.verify_state(state)
        info = await oauth.exchange_code(code)
    except OAuthError as exc:
        return RedirectResponse(f"{frontend}/?login_error={exc}", status_code=303)

    user = db.query(User).filter(User.google_sub == info["sub"]).one_or_none()
    if user is None:
        user = User(google_sub=info["sub"])
        db.add(user)
    user.email = info.get("email", "")
    user.name = info.get("name", "")
    user.picture = info.get("picture", "")
    user.last_login_at = utcnow()
    db.commit()

    response = RedirectResponse(f"{frontend}{next_path}", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        issue_token(user.id, settings.session_secret, settings.session_days),
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.public_base_url.startswith("https"),
        path="/",
    )
    return response


@router.get("/me", response_model=AccountResponse)
def me(user: UserDep, db: DbDep) -> AccountResponse:
    return _account(user, db)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/consent", response_model=AccountResponse)
def consent(request: ConsentRequest, user: UserDep, db: DbDep) -> AccountResponse:
    if not request.agreed:
        raise AppError("동의해야 서비스를 이용할 수 있습니다.")
    user.consented_at = datetime.now(UTC)
    db.commit()
    return _account(user, db)


@router.put("/api-key", response_model=AccountResponse)
async def set_api_key(
    request: ApiKeyRequest,
    user: UserDep,
    db: DbDep,
    cipher: CipherDep,
    settings: SettingsDep,
) -> AccountResponse:
    """키를 저장하기 전에 실제로 쓸 수 있는지 한 번 확인한다."""
    if not user.has_consented:
        raise AppError("먼저 이용 동의를 해 주세요.")

    provider_id = request.provider or keys.resolve(user, settings.app_mode).provider.id
    provider = registry.info(provider_id)
    if provider is None or not provider.implemented:
        raise AppError("지금 쓸 수 없는 제공자입니다.")
    if not provider.needs_key:
        raise AppError(f"{provider.label} 는 키가 필요하지 않습니다.")

    # 지금은 Gemini 하나뿐이다. 둘이 늘면 확인 방법도 제공자마다 갈린다 (M12-T3).
    if provider_id == registry.GEMINI:
        ok, detail = await verify_api_key(
            request.api_key,
            base_url=settings.gemini_base_url,
            model=provider.models[0],
        )
        if not ok:
            raise AppError(f"키를 확인하지 못했습니다. {detail or ''}".strip())

    keys.save(db, user.id, provider_id, request.api_key, cipher)
    db.commit()
    return _account(user, db)


@router.delete("/api-key", response_model=AccountResponse)
def delete_api_key(
    user: UserDep, db: DbDep, settings: SettingsDep, provider: str = ""
) -> AccountResponse:
    """키를 지운다. 제공자를 안 주면 지금 고른 것을 지운다."""
    provider_id = provider or keys.resolve(user, settings.app_mode).provider.id
    row = keys.row_for(db, user.id, provider_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return _account(user, db)


@router.put("/model", response_model=AccountResponse)
def choose_model(
    request: ActiveModelRequest, user: UserDep, db: DbDep, settings: SettingsDep
) -> AccountResponse:
    """쓸 제공자와 모델을 고른다 — **회원 전역 설정**이다.

    저장하는 순간부터 분석과 채점이 그것으로 간다. 고를 수 없는 것은 거부한다 —
    저장해 두고 나중에 기본값으로 떨어지면 회원은 자기가 고른 것으로 돌아간다고 믿는다.
    """
    allowed = {p.id: p for p in registry.selectable(settings.app_mode)}
    provider = allowed.get(request.provider)
    if provider is None:
        raise AppError("이 모드에서 고를 수 없는 제공자입니다.")
    if request.model and request.model not in provider.models:
        raise AppError("그 제공자가 제공하지 않는 모델입니다.")

    user.active_provider = provider.id
    user.active_model = request.model or provider.models[0]
    db.commit()
    return _account(user, db)


@router.delete("/account", response_model=DeletionSummary)
def delete_account(user: UserDep, db: DbDep, response: Response) -> DeletionSummary:
    """탈퇴. 기록과 계정을 지우고 세션 쿠키까지 없앤다.

    **이 라우터가 cloud 에서만 등록되므로** 로컬에서는 이 경로 자체가 없다.
    모드 분기를 코드에 쓰지 않아도 되는 자리다 (09-mode-matrix.md §3.6).

    암호화된 Gemini 키도 계정 행과 함께 사라진다. 따로 지울 필요가 없다.
    """
    deleted = account.delete_account(db, user.id)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return DeletionSummary(**deleted)
