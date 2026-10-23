"""데이터 레이어의 불변식. 규약은 14-data-layer.md.

**빼먹어도 그 표만 쓰는 기능은 멀쩡히 동작한다.** 드러나는 것은 탈퇴할 때와 두 번째
회원이 올 때인데, 둘 다 개발 중에는 안 일어난다. 그래서 주의력이 아니라 검사로 막는다.

전에는 격리를 지키는 검사가 **히스토리 읽기 하나**뿐이었다. 나의 표현 · 연습 기록 ·
데이터 삭제는 동작은 맞았지만 아무것도 지키고 있지 않았다.

[문서] plan/DONE.md M13-T2
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.auth.crypto import KeyCipher
from app.db import SHARED, Base, User, session_scope
from app.db.models import utcnow
from app.services.account import OWNED
from tests.modes import ENCRYPTION_KEY, login, make_cloud_user

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "documents" / "14-data-layer.md"
# 질의를 전수 조사할 범위. 라우터와 서비스가 DB 를 만지는 전부다.
SCANNED = ("app/routers", "app/services", "app/db")

OWNED_NAMES = {model.__name__ for model in OWNED}
SHARED_NAMES = {model.__name__ for model in SHARED}


# --------------------------------------------------------------- 스키마 불변식


def test_every_table_is_classified():
    """14 §3.7 — **`user_id` 가 없는 표는 두 가지다.**

    일부러 공용인 표와, 회원 소유로 만들려다 `user_id` 를 빠뜨린 표. 스키마만 봐서는
    **둘의 생김새가 같다.** 빠뜨린 쪽은 그 표만 쓰는 기능이 멀쩡히 동작하므로 개발
    중에는 드러나지 않고, 드러나는 것은 **두 번째 회원이 올 때**다 — 남의 데이터가
    보인다.

    그래서 공용이라면 `SHARED` 에 **적게** 한다. 적지 않으면 여기서 막힌다.
    """
    unclassified = []
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if model.__name__ == "User":
            continue
        has_user_id = "user_id" in model.__table__.columns
        declared_shared = model.__name__ in SHARED_NAMES
        if not has_user_id and not declared_shared:
            unclassified.append(model.__name__)

    assert not unclassified, (
        "어느 쪽인지 알 수 없는 표가 있다: " + ", ".join(sorted(unclassified)) + "\n"
        "  회원 것이면 user_id 를 달고 OWNED 에 더한다.\n"
        "  공용이면 models.py 의 SHARED 에 적는다 (14-data-layer.md §3.7)."
    )


def test_a_shared_table_carries_no_owner():
    """14 §3.7 — 공용 표에 회원을 가리키는 열이 생기면 **그 순간 공용이 아니다.**

    그대로 두면 탈퇴해도 안 지워지는 회원 데이터가 된다 — 3.4 가 막는 바로 그 버그가
    `SHARED` 에 숨어서 재발한다.
    """
    owned_looking = [m.__name__ for m in SHARED if "user_id" in m.__table__.columns]

    assert not owned_looking, (
        "공용이라 적어 놓고 user_id 를 들었다: " + ", ".join(sorted(owned_looking)) + "\n"
        "  회원 것이면 SHARED 에서 빼고 OWNED 로 옮긴다."
    )


def test_the_two_lists_do_not_overlap():
    """한 표가 양쪽에 있으면 탈퇴가 공용 데이터를 지운다."""
    both = OWNED_NAMES & SHARED_NAMES

    assert not both, f"OWNED 와 SHARED 양쪽에 있다: {sorted(both)}"


def test_owned_covers_every_table_that_has_a_user_id():
    """14 §3.4 — 빠뜨리면 탈퇴한 회원의 데이터가 남는다.

    회원은 "전부 지웠다" 는 답을 받고 데이터는 남는다. 개인정보 관점에서 가장 나쁜
    종류의 버그이고, 새 표를 만드는 사람은 `services/account.py` 를 열지 않는다.
    """
    with_user_id = {
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if "user_id" in mapper.class_.__table__.columns
    }

    assert with_user_id == OWNED_NAMES, (
        "user_id 를 든 모델과 OWNED 목록이 다르다.\n"
        f"  모델에만: {sorted(with_user_id - OWNED_NAMES)}\n"
        f"  OWNED 에만: {sorted(OWNED_NAMES - with_user_id)}"
    )


@pytest.mark.parametrize("model", OWNED, ids=lambda m: m.__tablename__)
def test_user_id_is_a_foreign_key_with_an_index(model):
    """주인 없는 행이 생기면 안 되고, 모든 질의가 이 칸으로 좁히므로 인덱스가 필요하다."""
    column = model.__table__.columns["user_id"]

    targets = {fk.target_fullname for fk in column.foreign_keys}
    assert targets == {"users.id"}, f"{model.__tablename__}.user_id 의 FK: {targets}"
    assert column.index, f"{model.__tablename__}.user_id 에 인덱스가 없다"


@pytest.mark.parametrize("model", OWNED, ids=lambda m: m.__tablename__)
def test_every_unique_constraint_includes_user_id(model):
    """14 §3.2 — 전역 유니크는 조용히 버그가 된다.

    `expression` 만으로 걸면 한 회원이 담은 표현을 다른 회원은 못 담는다.
    먼저 담은 회원에게는 아무 일도 안 일어나고 **나중 회원만 실패한다.**
    """
    from sqlalchemy import UniqueConstraint

    for constraint in model.__table__.constraints:
        if not isinstance(constraint, UniqueConstraint):
            continue
        columns = {column.name for column in constraint.columns}
        assert "user_id" in columns, (
            f"{model.__tablename__} 의 유니크 제약 {constraint.name} 에 user_id 가 없다: "
            f"{sorted(columns)}"
        )


def test_the_table_list_in_the_doc_matches_the_schema():
    """14 §2 의 표를 실제 스키마가 고정한다. 한쪽을 고치면 다른 쪽도 고치게 된다."""
    section = DOC.read_text(encoding="utf-8").split("## 2.")[1].split("## 3.")[0]
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", section, re.MULTILINE))
    actual = set(Base.metadata.tables)

    assert documented == actual, (
        "14 §2 의 표와 실제 테이블이 다르다.\n"
        f"  문서에만: {sorted(documented - actual)}\n"
        f"  스키마에만: {sorted(actual - documented)}"
    )


# ------------------------------------------------------- 질의가 user_id 로 좁는지


def _functions_touching_owned_models() -> list[tuple[str, str, ast.AST]]:
    """소유 모델을 직접 질의하는 함수들. (파일, 함수명, 노드)"""
    found = []
    for folder in SCANNED:
        for path in sorted((ROOT / "backend" / folder).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if _queries_owned_model(node):
                    found.append((str(path.relative_to(ROOT)), node.name, node))
    return found


def _queries_owned_model(node: ast.AST) -> bool:
    """`db.query(X)` · `db.get(X, ...)` · `select(X)` · `delete(X)` 에서 X 가 소유 모델인가."""
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not call.args:
            continue
        name = call.func.attr if isinstance(call.func, ast.Attribute) else None
        if name is None and isinstance(call.func, ast.Name):
            name = call.func.id
        if name not in {"query", "get", "select", "delete"}:
            continue
        first = call.args[0]
        if isinstance(first, ast.Name) and first.id in OWNED_NAMES:
            return True
    return False


def _mentions_user_id(node: ast.AST) -> bool:
    return any(
        isinstance(inner, ast.Attribute) and inner.attr == "user_id" for inner in ast.walk(node)
    )


def test_the_scan_actually_found_the_queries():
    """빈 목록을 훑으면 아래 검사가 통과만 한다. 찾았다는 것부터 확인한다."""
    found = _functions_touching_owned_models()

    assert len(found) >= 5, f"소유 모델을 질의하는 함수를 {len(found)}개만 찾았다"


def test_every_query_on_an_owned_model_narrows_by_user_id():
    """14 §3.1 — 좁히지 않은 질의 하나가 남의 데이터를 통째로 내준다.

    `db.get` 이 가장 위험하다. id 만 보므로 소유자 확인을 빼먹으면 **남의 기록 id 를
    찍어 읽을 수 있다.** 그래서 같은 함수 안에 `user_id` 가 반드시 나와야 한다.
    """
    naked = [
        f"{path}::{name}"
        for path, name, node in _functions_touching_owned_models()
        if not _mentions_user_id(node)
    ]

    assert not naked, "user_id 로 좁히지 않고 소유 모델을 질의한다:\n  " + "\n  ".join(naked)


# ------------------------------------------------------------------- 회원 격리

# 소유 데이터를 돌려주는 목록 경로 전부. 남의 계정에서는 모두 비어 보여야 한다.
LIST_PATHS = ("/api/history", "/api/vocabulary", "/api/practice/history")

PRACTICE = {
    "expression": "across the pond",
    "type": "관용구",
    "meaning": "대서양을 건너",
    "prompt_ko": "그녀의 소설은 대서양을 건너갔다.",
    "model_answer": "Her novel made it across the pond.",
    "learner_answer": "Her novel went across the pond",
}


def _stranger() -> int:
    """동의와 키 등록까지 끝낸 **다른** 회원. 문턱이 아니라 격리를 보려는 것이다."""
    with session_scope() as db:
        other = User(google_sub="sub-stranger", email="stranger@b.com")
        other.consented_at = utcnow()
        other.encrypted_api_key = KeyCipher(ENCRYPTION_KEY).encrypt("AIzaSyFAKEKEY1111")
        other.api_key_hint = "••••1111"
        db.add(other)
        db.flush()
        return other.id


@pytest.fixture
def two_members(cloud):
    """데이터를 쌓아 둔 회원과, 그 데이터를 노리는 다른 회원."""
    owner = make_cloud_user()
    login(cloud, owner)
    cloud.post("/api/analyze", json={"text": "across the pond"})
    cloud.post("/api/practice", json=PRACTICE)

    mine = {
        "history": cloud.get("/api/history").json()[0]["id"],
        "vocabulary": cloud.get("/api/vocabulary").json()[0]["id"],
    }
    assert all(cloud.get(path).json() for path in LIST_PATHS), "주인 데이터가 안 쌓였다"

    return cloud, owner, _stranger(), mine


@pytest.mark.parametrize("path", LIST_PATHS)
def test_another_members_rows_are_invisible(two_members, path):
    client, _owner, stranger, _mine = two_members
    login(client, stranger)

    assert client.get(path).json() == []


def test_narrowing_by_expression_does_not_leak(two_members):
    """나의 표현이 쓰는 `?expression=` 이 user_id 보다 먼저 걸리면 남의 기록이 나온다."""
    client, _owner, stranger, _mine = two_members
    login(client, stranger)

    rows = client.get("/api/practice/history", params={"expression": "across the pond"}).json()
    assert rows == []


@pytest.mark.parametrize(
    ("method", "template"),
    [
        ("get", "/api/history/{history}"),
        ("delete", "/api/history/{history}"),
        ("delete", "/api/vocabulary/{vocabulary}"),
    ],
)
def test_another_members_row_cannot_be_reached_by_id(two_members, method, template):
    """단건 경로가 구멍이다. id 를 찍어도 거부되어야 한다."""
    client, _owner, stranger, mine = two_members
    login(client, stranger)

    assert getattr(client, method)(template.format(**mine)).status_code != 200


def test_my_data_counts_only_my_own(two_members):
    client, _owner, stranger, _mine = two_members
    login(client, stranger)

    assert client.get("/api/account/data").json() == {
        "analyses": 0,
        "practices": 0,
        "vocabulary": 0,
        "usage_counters": 0,
    }


def test_purging_does_not_touch_another_member(two_members):
    """가장 나쁜 사고다. 남이 지우기를 눌러 내 데이터가 사라지면 복구할 길이 없다."""
    client, owner, stranger, _mine = two_members

    login(client, stranger)
    client.delete("/api/account/data")

    login(client, owner)
    for path in LIST_PATHS:
        assert len(client.get(path).json()) == 1, f"{path} 가 비었다"


def test_leaving_does_not_touch_another_member(two_members):
    """탈퇴는 표마다 명시적으로 지운다(14 §3.3). 그 삭제가 user_id 를 빼먹으면 전체가 날아간다."""
    client, owner, stranger, _mine = two_members

    login(client, stranger)
    assert client.delete("/api/auth/account").status_code == 200

    login(client, owner)
    for path in LIST_PATHS:
        assert len(client.get(path).json()) == 1, f"{path} 가 비었다"


def test_a_missing_row_and_another_members_row_answer_the_same(two_members):
    """**구별하지 않는 것이 규약이다** (03 · 14 §3.1).

    404 와 403 을 나눠 주면 "403 이 떴다 = 그 번호가 존재한다" 가 되고, 그것만으로
    다른 회원이 몇 건을 쌓았는지 셀 수 있다. 내용을 못 봐도 그건 이미 누출이다.

    상태 코드만 맞추면 메시지로 갈릴 수 있으므로 **본문까지** 같은지 본다.
    """
    client, _owner, stranger, mine = two_members
    login(client, stranger)

    missing = client.get("/api/history/999999")
    other = client.get(f"/api/history/{mine['history']}")

    assert missing.status_code == other.status_code == 404
    assert missing.json() == other.json()


@pytest.mark.parametrize(
    ("method", "template"),
    [
        ("get", "/api/history/{history}"),
        ("delete", "/api/history/{history}"),
        ("delete", "/api/vocabulary/{vocabulary}"),
    ],
)
def test_single_row_paths_answer_404(two_members, method, template):
    """단건 경로는 모두 404 다. 하나만 400 으로 남으면 거기서 존재가 드러난다."""
    client, _owner, stranger, mine = two_members
    login(client, stranger)

    response = getattr(client, method)(template.format(**mine))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
