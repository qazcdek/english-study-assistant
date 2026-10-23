"""운영자 — 공용 글감을 만드는 키의 주인 (M13-T5).

규약은 `app/services/operator.py` 머리말. **cloud 전용 기능**이라
local 부트스트랩 사용자에게는 플래그가 켜지지 않는다 (09-mode-matrix.md §3.8).
"""

import re
from pathlib import Path

from app.db import User, session_scope
from app.providers import registry
from app.services import operator

ROOT = Path(__file__).resolve().parents[2]
LEGAL = ROOT / "frontend" / "src" / "legal" / "operator.ts"


# ------------------------------------------- 이메일이 두 곳에서 갈라지지 않는다


def test_the_legal_file_can_actually_be_read():
    """**먼저 이것부터.** 경로가 틀리면 아래 대조가 빈 문자열끼리 비교하며 통과한다."""
    assert LEGAL.exists(), f"{LEGAL} 를 못 찾았다"
    assert "OPERATOR" in LEGAL.read_text(encoding="utf-8")


def test_the_backend_and_the_legal_documents_name_the_same_operator():
    """법적 문서의 연락처와 백엔드의 운영자가 어긋나면,
    **약관에 적힌 사람과 공용 글감 키의 주인이 달라진다.**"""
    found = re.search(r"연락처:\s*'([^']+)'", LEGAL.read_text(encoding="utf-8"))

    assert found, "operator.ts 에서 연락처를 못 읽었다"
    assert found.group(1) == operator.OPERATOR_EMAIL


def test_the_job_provider_is_one_we_actually_have():
    """목록에 없는 제공자 이름을 적어 두면 **공용 글감을 만들려는 순간** 터진다."""
    assert operator.JOB_PROVIDER in {p.id for p in registry.PROVIDERS}


# ------------------------------------------------------------ 플래그를 켜는 규칙


def test_the_operator_email_is_recognised():
    assert operator.is_operator_email(operator.OPERATOR_EMAIL, verified=True)


def test_another_email_is_not_the_operator():
    assert not operator.is_operator_email("someone@else.com", verified=True)


def test_an_unverified_email_is_never_the_operator():
    """플래그는 **키를 쓸 권한**이다. 검증되지 않은 주장으로는 켜지지 않는다."""
    assert not operator.is_operator_email(operator.OPERATOR_EMAIL, verified=False)


def test_case_and_spacing_do_not_let_the_operator_slip_through():
    """구글이 대문자로 주거나 공백이 붙어 와도 같은 사람이다."""
    assert operator.is_operator_email(f"  {operator.OPERATOR_EMAIL.upper()}  ", verified=True)


def test_an_empty_email_is_not_the_operator():
    assert not operator.is_operator_email("", verified=True)
    assert not operator.is_operator_email("   ", verified=True)


# ------------------------------------------------------------------ 찾아내기


def test_with_no_operator_there_is_nobody_to_borrow_a_key_from(cloud):
    """`None` 은 "공용 글감을 만들 수 없다" 는 뜻이다. 조용히 아무 회원이나 집으면 안 된다."""
    with session_scope() as db:
        db.add(User(google_sub="s1", email="a@b.c"))
        db.commit()

        assert operator.find(db) is None


def test_the_flagged_member_is_found(cloud):
    with session_scope() as db:
        db.add(User(google_sub="s1", email="a@b.c"))
        db.add(User(google_sub="s2", email=operator.OPERATOR_EMAIL, is_operator=True))
        db.commit()

        found = operator.find(db)

        assert found is not None
        assert found.email == operator.OPERATOR_EMAIL


# ------------------------------------------------------------------ 두 모드


def test_no_member_is_an_operator_just_by_existing(both_modes):
    """**어느 모드에서도 저절로 켜지지 않는다.**

    local 은 cloud 전용 기능이라 부트스트랩 사용자에게 안 켜고(09 §3.8),
    cloud 는 운영자가 로그인해야 켜진다. 둘 다 "기본은 꺼짐" 이다.
    """
    with session_scope() as db:
        members = db.query(User).all()

        assert members, "검사가 빈 목록을 훑고 있다"
        assert all(not u.is_operator for u in members)
        assert operator.find(db) is None


# ------------------------------------------------------- 로그인이 플래그를 켠다
# **플래그가 켜지는 유일한 자리다.** 여기 검사가 없으면 나머지는 전부 손으로 켠
# 플래그를 확인하는 것이고, 실제 경로는 아무것도 지키지 않는다.


def sign_in(client, monkeypatch, *, email: str, verified: bool = True, sub: str = "g-1"):
    """구글 콜백을 실제로 통과시킨다. 토큰 교환만 가로챈다."""
    from app.auth import google
    from app.routers import auth as auth_router

    async def fake_exchange(self, code: str) -> dict:
        return {"sub": sub, "email": email, "email_verified": verified, "name": "n"}

    monkeypatch.setattr(google.GoogleOAuth, "exchange_code", fake_exchange)
    monkeypatch.setattr(google.GoogleOAuth, "verify_state", lambda self, state: "/")

    resp = client.get(
        auth_router.CALLBACK_PATH, params={"code": "c", "state": "s"}, follow_redirects=False
    )
    assert resp.status_code == 303, resp.text
    assert "login_error" not in resp.headers.get("location", "")
    return resp


def flag_of(email: str) -> bool:
    with session_scope() as db:
        row = db.query(User).filter(User.email == email).one()
        return row.is_operator


def test_signing_in_as_the_operator_turns_the_flag_on(cloud, monkeypatch):
    sign_in(cloud, monkeypatch, email=operator.OPERATOR_EMAIL)

    assert flag_of(operator.OPERATOR_EMAIL)


def test_signing_in_as_anyone_else_leaves_it_off(cloud, monkeypatch):
    sign_in(cloud, monkeypatch, email="someone@else.com")

    assert not flag_of("someone@else.com")


def test_an_unverified_operator_email_does_not_turn_it_on(cloud, monkeypatch):
    """구글이 검증하지 않은 이메일로는 켜지지 않는다. **플래그는 키를 쓸 권한이다.**"""
    sign_in(cloud, monkeypatch, email=operator.OPERATOR_EMAIL, verified=False)

    assert not flag_of(operator.OPERATOR_EMAIL)


def test_the_flag_turns_off_when_the_email_changes(cloud, monkeypatch):
    """**한 번 켜고 두지 않는다.** 두면 운영자가 바뀐 뒤에도 옛 계정이 권한을 든다.

    같은 구글 계정(`sub`)이 다른 이메일로 돌아오는 경우다.
    """
    sign_in(cloud, monkeypatch, email=operator.OPERATOR_EMAIL, sub="g-same")
    assert flag_of(operator.OPERATOR_EMAIL)

    sign_in(cloud, monkeypatch, email="moved@else.com", sub="g-same")

    assert not flag_of("moved@else.com")
    with session_scope() as db:
        assert operator.find(db) is None
