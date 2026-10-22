"""제공자별 회원 키와 **활성 선택**을 읽고 쓴다.

전에는 키가 `users` 의 한 칸이었고 제공자가 하나였다. 둘 이상을 고를 수 있게
되면서(M12-T1) 세 가지가 함께 필요해졌다 —
어느 제공자·모델로 일하나, 그 제공자의 키가 있나, 그 키를 어떻게 꺼내나.

**한 곳에 모은다.** 흩어 두면 "지금 활성 제공자" 판단이 라우터·의존성·화면에서
각자 갈라지고, 갈라진 판단은 **키 없는 제공자로 호출을 시작하게** 만든다.

활성 선택은 **회원 전역 설정**이다. 바꿔 저장하면 그 뒤의 모든 작업이 그것으로 간다
(09-mode-matrix.md §3.2).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.auth.crypto import KeyCipher
from app.db import ProviderKey, User
from app.providers import registry


@dataclass(frozen=True)
class Choice:
    """지금 이 회원이 쓰는 제공자와 모델."""

    provider: registry.ProviderInfo
    model: str


def resolve(user: User, mode: str) -> Choice:
    """회원 설정 → 실제로 쓸 제공자와 모델.

    **고를 수 없는 것이 저장돼 있으면 기본값으로 떨어진다.** 모드가 바뀌거나
    제공자가 목록에서 빠질 수 있다 — 저장된 값을 그대로 믿으면 cloud 에서
    llama-server 를 부르려 든다.
    """
    allowed = {p.id: p for p in registry.selectable(mode)}
    chosen = allowed.get(user.active_provider) or registry.default_for(mode)
    model = user.active_model if user.active_model in chosen.models else chosen.models[0]
    return Choice(provider=chosen, model=model)


def row_for(db: Session, user_id: int, provider_id: str) -> ProviderKey | None:
    return (
        db.query(ProviderKey)
        .filter(ProviderKey.user_id == user_id, ProviderKey.provider == provider_id)
        .one_or_none()
    )


def providers_with_keys(db: Session, user_id: int) -> dict[str, str]:
    """제공자 → 끝 네 자리. 화면이 어디에 키가 있는지 보여주는 데 쓴다.

    **평문은 돌려주지 않는다.** 키는 서버 밖으로 나가지 않는다.
    """
    rows = db.query(ProviderKey).filter(ProviderKey.user_id == user_id).all()
    return {row.provider: row.hint for row in rows}


def has_key(db: Session, user: User, choice: Choice) -> bool:
    """그 제공자로 호출할 수 있나. 키가 필요 없는 제공자(내 PC)는 항상 참이다."""
    if not choice.provider.needs_key:
        return True
    return row_for(db, user.id, choice.provider.id) is not None


def save(db: Session, user_id: int, provider_id: str, api_key: str, cipher: KeyCipher) -> ProviderKey:
    """키를 넣거나 바꾼다. 같은 제공자에 두 개를 두지 않는다."""
    row = row_for(db, user_id, provider_id)
    if row is None:
        row = ProviderKey(user_id=user_id, provider=provider_id)
        db.add(row)
    row.encrypted = cipher.encrypt(api_key)
    # 화면에는 끝 네 자리만. 평문은 보관하지 않는다.
    row.hint = f"••••{api_key[-4:]}" if len(api_key) >= 4 else "••••"
    return row


def decrypt(db: Session, user_id: int, provider_id: str, cipher: KeyCipher) -> str:
    row = row_for(db, user_id, provider_id)
    return cipher.decrypt(row.encrypted) if row is not None else ""
