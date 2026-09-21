"""회원 Gemini API 키 암호화.

키는 회원 본인의 것이고 그 사람의 사용 한도가 소모되므로, 평문으로 두지 않는다.
`ENCRYPTION_KEY` 가 유출되지 않는 한 DB 만으로는 복호화할 수 없다.
"""

from cryptography.fernet import Fernet, InvalidToken


class KeyCipher:
    def __init__(self, encryption_key: str) -> None:
        self._fernet = Fernet(encryption_key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("저장된 API 키를 복호화할 수 없습니다.") from exc

    @staticmethod
    def generate_key() -> str:
        """운영 배포 전에 한 번 만들어 ENCRYPTION_KEY 에 넣는다."""
        return Fernet.generate_key().decode()


def key_hint(api_key: str) -> str:
    """화면에 보여줄 마지막 네 자리. 키 전체는 절대 다시 내보내지 않는다."""
    tail = api_key.strip()[-4:]
    return f"••••{tail}" if tail else ""
