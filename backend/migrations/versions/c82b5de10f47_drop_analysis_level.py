"""drop analysis level

분석에서 난이도를 걷어낸다 (M16). 중급 분석이 **유일한** 분석이 되고 초급·상급은
사라진다. 난이도는 작문 연습의 **예문**으로 옮겨 갔다.

`08 §1` 이 이미 그 진단을 적어 뒀다 — *"난이도가 실제로 바꾸는 것은 프롬프트에
끼워 넣는 문단 하나뿐 … 전부 형용사와 정도부사다. 어떤 출력이 충분히 깊은지 판정할
기준이 없어 검증도 못 한다."*

### 유니크를 좁힌다

`paragraph_analyses` 는 `(문단, 난이도)` 마다 한 행이었다. 난이도가 없어지면
**문단마다 한 행**이고, 좁히지 않으면 같은 문단에 행이 둘 설 수 있다.

### 저장된 값을 버리지만 기록은 남는다

`analyses.level` 에 `beginner`/`advanced` 로 저장된 회원 기록이 있을 수 있다.
그 값을 옮길 곳이 없다 — 분석 결과 자체는 그대로 읽히고(난이도는 설명의 깊이만
바꿨다) 어느 난이도로 돌렸는지만 사라진다. `downgrade` 는 칸을 되살리되
전부 `intermediate` 로 둔다. **그 값은 복원되지 않는다.**

Revision ID: c82b5de10f47
Revises: b4e9f1c37a05
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c82b5de10f47"
down_revision: str | None = "b4e9f1c37a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # **유니크를 먼저 바꾼다.** 칸을 지우면 그 칸을 쓰는 제약이 함께 사라지거나
    # (Postgres) 남아서 거부당한다 — 순서를 분명히 둔다.
    with op.batch_alter_table("paragraph_analyses") as batch:
        batch.drop_constraint("uq_analysis_paragraph_level", type_="unique")
        batch.create_unique_constraint("uq_analysis_paragraph", ["paragraph_id"])
        batch.drop_column("level")

    op.drop_column("analyses", "level")


def downgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("level", sa.String(length=20), nullable=False, server_default="intermediate"),
    )
    with op.batch_alter_table("paragraph_analyses") as batch:
        batch.add_column(
            sa.Column(
                "level", sa.String(length=20), nullable=False, server_default="intermediate"
            )
        )
        batch.drop_constraint("uq_analysis_paragraph", type_="unique")
        batch.create_unique_constraint(
            "uq_analysis_paragraph_level", ["paragraph_id", "level"]
        )
