"""스키마는 Alembic 이 만든다.

전에는 앱이 뜰 때 `create_all` 로 테이블을 만들었다. 그러면 **컬럼이 바뀔 때 손이 가고**,
무엇보다 배포된 DB 와 모델이 어긋난 것을 아무도 모른다 (07-web-deployment.md §8).

Render 무료 티어에는 배포 전 단계(release phase)가 없으므로 **앱이 뜰 때 올린다.**
마이그레이션 하나는 수십 밀리초라 콜드 스타트에 영향이 없다.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.db.models import Base
from app.db.session import normalize_url

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # script_location 은 ini 기준 상대 경로라 어디서 실행해도 같은 곳을 보게 못 박는다.
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    return cfg


def _table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return set(inspect(conn).get_table_names())
    finally:
        engine.dispose()


def upgrade_to_head() -> None:
    """DB 를 최신 스키마로 올린다.

    **한 번만 필요한 분기가 있다.** 이미 `create_all` 로 만들어진 DB(로컬 개발용과
    배포본)에는 테이블이 있는데 `alembic_version` 이 없다. 거기에 `upgrade` 를 걸면
    "이미 있는 테이블" 로 실패한다. 그래서 그 경우에만 **첫 리비전을 찍고 넘어간다** —
    지금 스키마가 첫 리비전과 같기 때문에 안전하다.

    두 DB 가 모두 넘어온 뒤에는 이 분기를 지운다 (07-web-deployment.md §8).
    """
    url = normalize_url(get_settings().database_url)
    tables = _table_names(url)
    known = {table.name for table in Base.metadata.sorted_tables}

    cfg = _config()
    if "alembic_version" not in tables and tables & known:
        command.stamp(cfg, "head")
        return
    command.upgrade(cfg, "head")
