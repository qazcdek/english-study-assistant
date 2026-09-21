"""Google 로그인과 계정 설정."""

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.auth.crypto import key_hint
from app.auth.google import GoogleOAuth, OAuthError
from app.auth.session import COOKIE_NAME, issue_token
from app.db import User
from app.db.models import utcnow
from app.deps import CipherDep, DbDep, SettingsDep, UserDep
from app.errors import AppError
from app.providers.gemini import verify_api_key
from app.schemas import AccountResponse, ApiKeyRequest, ConsentRequest

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


def _account(user: User) -> AccountResponse:
    return AccountResponse(
        email=user.email,
        name=user.name,
        picture=user.picture,
        has_consented=user.has_consented,
        has_api_key=user.has_api_key,
        api_key_hint=user.api_key_hint,
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
def me(user: UserDep) -> AccountResponse:
    return _account(user)


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
    return _account(user)


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

    ok, detail = await verify_api_key(
        request.api_key,
        base_url=settings.gemini_base_url,
        model=settings.gemini_model,
    )
    if not ok:
        raise AppError(f"키를 확인하지 못했습니다. {detail or ''}".strip())

    user.encrypted_api_key = cipher.encrypt(request.api_key)
    user.api_key_hint = key_hint(request.api_key)
    db.commit()
    return _account(user)


@router.delete("/api-key", response_model=AccountResponse)
def delete_api_key(user: UserDep, db: DbDep) -> AccountResponse:
    user.encrypted_api_key = None
    user.api_key_hint = ""
    db.commit()
    return _account(user)
