"""검사가 **어느 엔진에서 돌고 있는지**를 검사가 확인한다.

H-032 를 고치면서 CI 에 Postgres 서비스를 붙였고 통과했다. 그런데 **통과만으로는
아무것도 모른다** — `TEST_DATABASE_URL` 이 안 먹어도 SQLite 로 조용히 되돌아가서
똑같이 통과한다. 컨테이너는 떴는데 아무도 안 쓰는 상태가 가장 나쁘다:
"운영 엔진을 본다" 고 믿으면서 실제로는 전과 똑같다.

그래서 두 방향에서 못박는다.

- **지금 이 판이 환경이 지시한 엔진에서 돌고 있나** — 조용한 되돌아감을 잡는다
- **CI 가 Postgres 를 지시하고 있나** — 서비스나 env 를 지우는 것을 잡는다

(CLAUDE.md §7 "검사는 실패하는 것을 확인하고 믿는다")
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.engine import make_url

from tests import dbs

CI_YML = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_the_engine_follows_what_the_environment_asked_for(db_url):
    """환경이 Postgres 를 가리키면 **실제로 Postgres 에서 돌아야 한다.**

    이 검사가 없으면 `TEST_DATABASE_URL` 의 오타 하나로 전부 SQLite 로 되돌아가고,
    CI 는 초록인 채로 **아무것도 더 못 잡는 상태**가 된다.
    """
    asked = os.environ.get(dbs.ENV_VAR, "").strip()
    actual = make_url(db_url).get_backend_name()

    if asked:
        assert actual == "postgresql", (
            f"{dbs.ENV_VAR} 가 Postgres 를 가리키는데 검사는 {actual} 에서 돌고 있다"
        )
    else:
        assert actual == "sqlite", f"{dbs.ENV_VAR} 가 비었는데 {actual} 로 붙었다"


def test_each_test_gets_its_own_namespace(db_url):
    """격리가 **실제로** 걸려 있나.

    Postgres 면 `search_path` 가 그 판 전용 스키마로 고정돼 있어야 한다. `public` 에
    떨어지면 406개가 같은 표를 공유하면서 서로의 행을 지운다.
    """
    if make_url(db_url).get_backend_name() != "postgresql":
        pytest.skip("SQLite 는 파일 하나가 곧 격리다")

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    engine = create_engine(db_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            path = conn.execute(text("show search_path")).scalar()
    finally:
        engine.dispose()

    assert path and path != "public", f"search_path 가 가둬지지 않았다: {path!r}"
    assert path.startswith("t_"), f"테스트 전용 스키마가 아니다: {path!r}"


# ------------------------------------------------- CI 가 Postgres 를 지시하나


@pytest.fixture(scope="module")
def backend_job() -> dict:
    assert CI_YML.is_file(), f"{CI_YML} 를 읽을 수 없다"
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8"))["jobs"]["backend"]


def test_ci_brings_up_a_postgres_matching_production(backend_job):
    """**머지 게이트가 운영 엔진을 본다.** 서비스를 지우면 여기서 걸린다.

    메이저 버전도 맞춘다 — 운영(Neon)과 로컬 도커가 모두 17 이다
    (09-mode-matrix.md §6.4).
    """
    service = backend_job.get("services", {}).get("postgres")
    assert service, "CI backend 잡에 postgres 서비스가 없다"
    assert service["image"].startswith("postgres:17"), (
        f"운영은 Postgres 17 이다. CI 는 {service['image']} 를 띄운다"
    )


def test_ci_actually_points_the_suite_at_it(backend_job):
    """서비스를 띄워 놓고 **안 쓰는 것**이 가장 나쁘다 — 초록인데 전과 똑같다."""
    steps = [s for s in backend_job["steps"] if s.get("name") == "pytest"]
    assert len(steps) == 1, "CI 의 pytest 단계를 찾지 못했다"

    url = steps[0].get("env", {}).get(dbs.ENV_VAR, "")
    assert url, f"CI 의 pytest 단계가 {dbs.ENV_VAR} 를 주지 않는다"
    assert make_url(url).get_backend_name() == "postgresql", (
        f"{dbs.ENV_VAR} 가 Postgres 가 아니다: {url}"
    )
