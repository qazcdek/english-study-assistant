"""세션 쿠키. JWT 를 HttpOnly 쿠키에 담는다."""

from datetime import UTC, datetime, timedelta

import jwt

COOKIE_NAME = "eng_session"
ALGORITHM = "HS256"


def issue_token(user_id: int, secret: str, days: int) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(days=days)}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def read_token(token: str, secret: str) -> int | None:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
