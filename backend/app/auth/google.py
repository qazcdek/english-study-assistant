"""Google OAuth 2.0 Authorization Code 흐름.

로그인은 **신원 확인에만** 쓴다. Google 로그인으로는 회원의 Gemini 사용 한도에
접근할 수 없기 때문에, LLM 호출에 쓸 API 키는 회원이 따로 등록한다
(documents/07-web-deployment.md 참고).
"""

from typing import Any
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

# 신원 확인에 필요한 최소 범위만 요청한다.
SCOPES = "openid email profile"
STATE_MAX_AGE = 600  # 10분


class OAuthError(Exception):
    pass


class GoogleOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._serializer = URLSafeTimedSerializer(secret, salt="google-oauth-state")

    def authorization_url(self, next_path: str = "/") -> str:
        state = self._serializer.dumps({"next": next_path})
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{AUTH_ENDPOINT}?{urlencode(params)}"

    def verify_state(self, state: str) -> str:
        try:
            data = self._serializer.loads(state, max_age=STATE_MAX_AGE)
        except BadSignature as exc:
            raise OAuthError("로그인 요청이 만료되었거나 위조되었습니다.") from exc
        return data.get("next", "/")

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code >= 400:
                raise OAuthError(f"토큰 교환에 실패했습니다: {token_resp.text[:200]}")

            access_token = token_resp.json().get("access_token")
            if not access_token:
                raise OAuthError("access_token 이 응답에 없습니다.")

            info_resp = await client.get(
                USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
            )
            if info_resp.status_code >= 400:
                raise OAuthError(f"사용자 정보를 가져오지 못했습니다: {info_resp.text[:200]}")

        info = info_resp.json()
        if not info.get("sub"):
            raise OAuthError("Google 계정 식별자를 받지 못했습니다.")
        return info
