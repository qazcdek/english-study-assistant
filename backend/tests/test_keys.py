"""제공자별 키와 **활성 선택**. 규약은 09-mode-matrix.md §3.2.

활성 선택은 회원 전역 설정이고 **저장된 값을 그대로 믿지 않는다** — 모드가 바뀌거나
제공자가 목록에서 빠질 수 있다. 그대로 믿으면 **cloud 에서 llama-server 를 부르려 든다.**
"""

import pytest

from app.db import ProviderKey, User
from app.providers import registry
from app.services import keys


def member(provider: str = "", model: str = "") -> User:
    return User(
        id=1, google_sub="s", email="a@b.com", active_provider=provider, active_model=model
    )


def test_an_empty_setting_falls_back_to_the_mode_default():
    """아직 안 고른 회원. 모드별로 전에 쓰던 것과 같아야 한다."""
    assert keys.resolve(member(), "local").provider.id == registry.LLAMA
    assert keys.resolve(member(), "cloud").provider.id == registry.GEMINI


def test_a_provider_that_this_mode_cannot_choose_falls_back():
    """**이것이 ③ 이었다.** local 에서 llama 를 고른 회원이 cloud 로 들어오면,
    저장된 값을 그대로 믿는 코드는 **Render 에서 내 PC 의 서버를 부르려 든다.**"""
    chosen = keys.resolve(member(registry.LLAMA), "cloud")

    assert chosen.provider.id == registry.GEMINI


def test_a_provider_that_is_not_implemented_falls_back():
    """목록에 있지만 아직 안 되는 것이 저장될 수 있다 (나중에 빠질 수도 있다)."""
    chosen = keys.resolve(member(registry.ANTHROPIC), "cloud")

    assert chosen.provider.implemented


def test_an_unknown_provider_falls_back():
    assert keys.resolve(member("있을-리-없는-것"), "cloud").provider.id == registry.GEMINI


def test_a_model_the_provider_does_not_offer_falls_back_to_its_first():
    """모델만 틀린 경우. 제공자는 맞으니 그 제공자의 기본 모델로 간다."""
    chosen = keys.resolve(member(registry.GEMINI, "gemini-없는모델"), "cloud")

    assert chosen.model == registry.BY_ID[registry.GEMINI].models[0]


def test_a_valid_choice_is_kept():
    gemini = registry.BY_ID[registry.GEMINI]
    chosen = keys.resolve(member(registry.GEMINI, gemini.models[0]), "local")

    assert chosen.provider.id == registry.GEMINI
    assert chosen.model == gemini.models[0]


# ------------------------------------------------------------------ 키


@pytest.fixture
def db(monkeypatch, tmp_path):
    from app.config import get_settings
    from app.db import init_engine, session_scope

    monkeypatch.setenv("APP_MODE", "local")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/k.db")
    get_settings.cache_clear()
    init_engine(get_settings().database_url, create_all=True)
    with session_scope() as session:
        session.add(User(id=1, google_sub="s", email="a@b.com"))
        session.flush()
        yield session
    get_settings.cache_clear()


def test_a_key_is_stored_encrypted_and_only_the_tail_is_shown(db):
    from app.auth.crypto import KeyCipher

    cipher = KeyCipher(KeyCipher.generate_key())
    keys.save(db, 1, registry.GEMINI, "AIzaSyREALKEY1234", cipher)
    db.flush()

    row = keys.row_for(db, 1, registry.GEMINI)
    assert row is not None
    # 평문이 그대로 들어가면 DB 를 읽는 누구나 회원 키를 쓴다.
    assert "AIzaSyREALKEY1234" not in row.encrypted
    assert cipher.decrypt(row.encrypted) == "AIzaSyREALKEY1234"
    assert row.hint == "••••1234"


def test_saving_twice_replaces_instead_of_piling_up(db):
    from app.auth.crypto import KeyCipher

    cipher = KeyCipher(KeyCipher.generate_key())
    keys.save(db, 1, registry.GEMINI, "AIzaSyFIRST0000", cipher)
    db.flush()
    keys.save(db, 1, registry.GEMINI, "AIzaSySECOND1111", cipher)
    db.flush()

    rows = db.query(ProviderKey).filter(ProviderKey.user_id == 1).all()
    assert len(rows) == 1
    assert cipher.decrypt(rows[0].encrypted) == "AIzaSySECOND1111"


def test_the_plaintext_never_comes_back_in_the_listing(db):
    from app.auth.crypto import KeyCipher

    cipher = KeyCipher(KeyCipher.generate_key())
    keys.save(db, 1, registry.GEMINI, "AIzaSyREALKEY1234", cipher)
    db.flush()

    held = keys.providers_with_keys(db, 1)
    assert held == {registry.GEMINI: "••••1234"}
    assert "AIzaSyREALKEY1234" not in repr(held)


def test_a_provider_without_a_key_is_not_ready(db):
    user = db.get(User, 1)
    gemini = keys.Choice(provider=registry.BY_ID[registry.GEMINI], model="gemini-3.5-flash-lite")

    assert keys.has_key(db, user, gemini) is False


def test_a_provider_that_needs_no_key_is_always_ready(db):
    """내 PC 의 llama-server 다. 키를 요구하면 로컬에서 아무것도 못 한다."""
    user = db.get(User, 1)
    llama = keys.Choice(provider=registry.BY_ID[registry.LLAMA], model="local-model")

    assert keys.has_key(db, user, llama) is True
