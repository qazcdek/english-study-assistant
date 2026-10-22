"""keys per provider

제공자가 둘 이상 생기면서(M12-T1) 키를 `users` 의 한 칸으로 담을 수 없게 됐다.
`provider_keys` 로 옮기고, 어느 제공자·모델로 일하는지를 회원 설정으로 둔다.

**이 리비전의 위험은 구조가 아니라 데이터다.** autogenerate 는 열을 만들고 지우기만
하고 **값을 옮기지 않는다** — 그대로 돌리면 모든 회원의 키가 사라진다. `ENCRYPTION_KEY`
는 교체할 수 없으므로 잃으면 복구할 길도 없다. 그래서 **지우기 전에 옮기고**,
옮긴 뒤 복호화되는지를 `test_migrations.py` 가 실제 Fernet 토막으로 확인한다.

Revision ID: 5223c473d9fc
Revises: c80f88bac834
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5223c473d9fc"
down_revision: str | None = "c80f88bac834"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 전에는 제공자가 하나였으므로, 남아 있는 키는 전부 Gemini 것이다.
LEGACY_PROVIDER = "gemini"

_keys = sa.table(
    "provider_keys",
    sa.column("user_id", sa.Integer),
    sa.column("provider", sa.String),
    sa.column("encrypted", sa.Text),
    sa.column("hint", sa.String),
    sa.column("created_at", sa.DateTime),
)
_users = sa.table(
    "users",
    sa.column("id", sa.Integer),
    sa.column("encrypted_api_key", sa.Text),
    sa.column("api_key_hint", sa.String),
)


def upgrade() -> None:
    op.create_table(
        "provider_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        # **Text 다.** 재 보니 SQLite 는 길이를 무시하고 그냥 넣고 Postgres 는
        # `value too long` 으로 거부한다 — 짧은 열은 테스트를 통과하고 **배포 때**
        # 마이그레이션이 죽는다.
        sa.Column("encrypted", sa.Text(), nullable=False),
        sa.Column("hint", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_key_user_provider"),
    )
    op.create_index(op.f("ix_provider_keys_user_id"), "provider_keys", ["user_id"])

    # 기존 행이 있으므로 server_default 를 준다. 없으면 NOT NULL 추가가 실패한다.
    op.add_column(
        "users",
        sa.Column("active_provider", sa.String(length=20), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("active_model", sa.String(length=80), nullable=False, server_default=""),
    )

    # **지우기 전에 옮긴다.** 빈 값은 옮기지 않는다 — 키를 등록한 적 없는 회원에게
    # 빈 행을 만들면 "키가 있다" 로 보인다.
    op.get_bind().execute(
        _keys.insert().from_select(
            ["user_id", "provider", "encrypted", "hint", "created_at"],
            sa.select(
                _users.c.id,
                sa.literal(LEGACY_PROVIDER),
                _users.c.encrypted_api_key,
                _users.c.api_key_hint,
                sa.func.now(),
            ).where(
                _users.c.encrypted_api_key.is_not(None),
                _users.c.encrypted_api_key != "",
            ),
        )
    )

    op.drop_column("users", "api_key_hint")
    op.drop_column("users", "encrypted_api_key")


def downgrade() -> None:
    """키를 되돌려 놓는다.

    **구조만 되돌리면 키가 사라진다.** 배포를 물려야 하는 날 그걸 발견하면 늦다.
    """
    op.add_column("users", sa.Column("encrypted_api_key", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("api_key_hint", sa.String(length=16), nullable=False, server_default=""),
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.select(_keys.c.user_id, _keys.c.encrypted, _keys.c.hint).where(
            _keys.c.provider == LEGACY_PROVIDER
        )
    ).all()
    for user_id, encrypted, hint in rows:
        bind.execute(
            sa.update(_users)
            .where(_users.c.id == user_id)
            .values(encrypted_api_key=encrypted, api_key_hint=hint)
        )

    op.drop_index(op.f("ix_provider_keys_user_id"), table_name="provider_keys")
    op.drop_table("provider_keys")
    op.drop_column("users", "active_model")
    op.drop_column("users", "active_provider")
