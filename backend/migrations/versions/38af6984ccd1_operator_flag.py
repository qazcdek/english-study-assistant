"""operator flag

공용 글감을 만드는 데 쓸 키의 주인을 표시한다 (M13-T5). cloud 전용 기능이다.

**autogenerate 가 낸 것을 그대로 쓰면 깨진다.** `nullable=False` 인데 기본값이
없어서 **기존 행이 있는 표에서는 `column contains null values` 로 거부당한다.**
`create_all` 로 비어 있는 테스트 DB 에서는 통과하고 **배포본에서만 깨지는** 종류의
어긋남이다 (14-data-layer.md §3.3 과 같은 방향). 그래서 `server_default` 를 준다.

### 기존 행에 플래그를 켜지 않는다

여기서 `UPDATE … WHERE email = '…'` 를 적고 싶어지지만 **적지 않는다.** 운영자
이메일이 `app/services/operator.py` 와 `frontend/src/legal/operator.ts` 두 곳에
있고 그 둘은 검사가 대조한다. 마이그레이션에 **세 번째 사본**을 두면 아무 장치도
그것을 보지 않는다 — 운영자가 바뀌는 날 조용히 틀린 채로 남는다.

대신 **로그인할 때 맞춰진다** (`routers/auth.py`). 운영자가 한 번 로그인하면
켜지고, 그때까지는 공용 글감이 만들어지지 않는다.

Revision ID: 38af6984ccd1
Revises: c05413ac849f
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "38af6984ccd1"
down_revision: str | None = "c05413ac849f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_operator", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(op.f("ix_users_is_operator"), "users", ["is_operator"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_is_operator"), table_name="users")
    op.drop_column("users", "is_operator")
