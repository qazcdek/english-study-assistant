"""article pick attempts

글감 고르기 실패를 적어 두는 공용 표 (M13-T4). **쿨다운의 근거다** —
실패 시각으로부터 5분 이내에는 다시 시도하지 않는다.

메모리에 두지 않는 이유는 배포 환경이다. Render 무료 티어는 15분 미사용이면
잠들고, 깨어날 때마다 쿨다운을 잊고 즉시 재시도한다 — **막으려던 바로 그
상황에서 안 막힌다.**

Revision ID: b4e9f1c37a05
Revises: a1c7e4d20b93
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e9f1c37a05"
down_revision: str | None = "a1c7e4d20b93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_pick_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("picked_for", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("picked_for", "source", name="uq_pick_attempt_day_source"),
    )
    op.create_index(
        op.f("ix_article_pick_attempts_picked_for"),
        "article_pick_attempts",
        ["picked_for"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_article_pick_attempts_picked_for"), table_name="article_pick_attempts"
    )
    op.drop_table("article_pick_attempts")
