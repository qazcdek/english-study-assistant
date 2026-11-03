"""article pipeline version

기사를 **어느 파이프라인이 만들었나** (M13-T15). 지금 값보다 낮으면 문단 묶음이나
발췌 범위가 낡은 것이므로 버리고 다시 받는다.

### 왜 추측하지 않나

문단 수나 글자 수로 "낡았다" 를 추정하면 **경계에 걸린 멀쩡한 기사를 버린다.**
숫자는 우리가 규칙을 바꿀 때만 올라간다.

`server_default="0"` 이다. 기존 행은 전부 0 — 이 칸이 생기기 전에 앉힌 것이고,
그것이 바로 다시 받아야 하는 상태다.

Revision ID: d3f81a9c62e7
Revises: c82b5de10f47
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3f81a9c62e7"
down_revision: str | None = "c82b5de10f47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("pipeline", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("articles", "pipeline")
