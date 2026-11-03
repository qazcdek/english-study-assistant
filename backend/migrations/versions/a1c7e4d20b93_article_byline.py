"""article byline

기자 크레딧을 둘 칸 하나 (M13-T10). **출처 약관이 요구하는 표기다** — 번역을
보여주는 화면에 기자 이름과 원문 출처를 명확히 적어야 한다.

`server_default=""` 를 준다. `nullable=False` 인데 기본값이 없으면 **기존 행이
있는 표에서 `column contains null values` 로 거부당하고**, `create_all` 로 비어
있는 검사 DB 에서는 통과해 **배포본에서만 깨진다** (`38af6984ccd1` 과 같은 조심).

### 기존 행의 크레딧을 여기서 채우지 않는다

채울 값을 알려면 **가디언 API 를 쳐야** 하고, 마이그레이션이 네트워크를 타면
키 없이 도는 환경에서 배포가 멈춘다. 빈 크레딧으로 남고, 그 기사는 다시 앉힐 때
`ArticleCreditError` 로 거부된다 — **조용히 크레딧 없이 보여지지 않는다.**

Revision ID: a1c7e4d20b93
Revises: 38af6984ccd1
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c7e4d20b93"
down_revision: str | None = "38af6984ccd1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("byline", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("articles", "byline")
