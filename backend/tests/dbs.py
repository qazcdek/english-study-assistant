"""테스트가 쓸 **빈 DB 하나**를 내준다.

기본은 임시 SQLite 다 — 빠르고, 파일이라 서로 간섭하지 않고 오프라인에서 돈다.
그런데 **운영은 Postgres 이고, 엔진이 다르면 통과한 검사가 배포에서 깨진다** (H-032).

이미 두 번 물렸고 **둘 다 글로만 막아 두고 있었다.** `String` 길이를 SQLite 는
무시하고 Postgres 는 `value too long` 으로 거부하며 (`tests/test_migrations.py` 의
주석), SQLite 는 `PRAGMA foreign_keys` 가 꺼져 있으면 CASCADE 가 아예 안 돈다
(14-data-layer.md §3.3). "그러니 조심해라" 는 장치가 아니다 (12-tooling.md §6).

그래서 `TEST_DATABASE_URL` 이 있으면 그 Postgres 에서 돈다. **CI 가 그쪽을 맡는다**
(`.github/workflows/ci.yml`) — 머지 게이트가 운영 엔진을 보면 되고, 로컬 반복
속도는 SQLite 로 둔다. 로컬에서 같이 보려면 `./dev.sh test --pg`.

### 왜 DB 가 아니라 스키마인가

테스트마다 `CREATE DATABASE` 를 하면 느리고, 하나를 공유하면 서로의 행을 지운다.
그래서 테스트마다 **스키마 하나**를 만들고 `search_path` 를 거기로 고정한다.
`public` 이 `search_path` 에서 빠지므로 **옆 테스트의 표가 아예 안 보인다.**

고정을 **주소에 실어** 보낸다 (`options=-csearch_path%3D…`). 그래서 앱 코드도
Alembic 도 고칠 데가 없다 — 둘 다 `DATABASE_URL` 을 그대로 쓴다.
"""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.db.session import normalize_url

ENV_VAR = "TEST_DATABASE_URL"

# Postgres 식별자 한계. 넘으면 **거부가 아니라 조용히 잘려서** 두 테스트가 같은
# 스키마를 보게 된다. 그래서 꼬리 자리를 미리 비워 둔다.
MAX_IDENT = 63


@contextmanager
def empty_database(tmp_path: Path) -> Iterator[str]:
    """빈 DB 주소를 하나 내주고, 끝나면 치운다."""
    base = normalize_url(os.environ.get(ENV_VAR, "").strip())
    if not base:
        yield f"sqlite+pysqlite:///{tmp_path}/test.db"
        return

    if base.startswith("sqlite"):
        # SQLite 로 돌리고 싶으면 값을 **비우면** 된다. 여기에 SQLite 주소를 적으면
        # "Postgres 에서 돌고 있다" 고 믿으면서 아무것도 더 못 잡는 상태가 된다.
        raise RuntimeError(f"{ENV_VAR} 는 Postgres 여야 한다. SQLite 는 값을 비워 두면 된다.")

    with _schema(base, tmp_path) as schema:
        joiner = "&" if "?" in base else "?"
        yield f"{base}{joiner}options=-csearch_path%3D{schema}"


@contextmanager
def _schema(base: str, tmp_path: Path) -> Iterator[str]:
    """스키마를 만들고 **끝나면 반드시 지운다.** 남기면 판을 돌릴수록 쌓인다."""
    name = _schema_name(tmp_path)
    admin = create_engine(base, poolclass=NullPool)
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{name}"'))
        try:
            yield name
        finally:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
    finally:
        admin.dispose()


def _schema_name(tmp_path: Path) -> str:
    """스키마 이름에 **테스트 이름을 남긴다** — 중간에 터졌을 때 어느 판인지 보려고.

    `tmp_path` 의 마지막 칸이 이미 테스트 이름에서 만들어진다. 무작위 꼬리는 지난
    판이 죽어 스키마가 남았을 때 `CREATE SCHEMA` 가 부딪히지 않게 한다 — 같은
    이름을 지우고 다시 만들면, 동시에 돌 때 남의 것을 지운다.
    """
    tail = secrets.token_hex(3)
    room = MAX_IDENT - len("t_") - len(tail) - 1
    stem = re.sub(r"[^a-z0-9_]", "_", tmp_path.name.lower())[:room]
    return f"t_{stem}_{tail}"
