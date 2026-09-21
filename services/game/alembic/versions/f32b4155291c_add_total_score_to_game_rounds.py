"""add total_score to game_rounds

Revision ID: f32b4155291c
Revises: b2a7f5e9c3d1
Create Date: 2026-09-21 16:10:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f32b4155291c'
down_revision: Union[str, Sequence[str], None] = 'b2a7f5e9c3d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("game_rounds", sa.Column("total_score", sa.Integer(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, data FROM game_rounds")).fetchall()
    for round_id, data in rows:
        total = sum(a["score"] for a in json.loads(data)["answers"])
        conn.execute(
            sa.text("UPDATE game_rounds SET total_score = :total WHERE id = :id"),
            {"total": total, "id": round_id},
        )

    op.alter_column("game_rounds", "total_score", nullable=False)
    op.create_index("ix_game_rounds_total_score", "game_rounds", ["total_score"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_game_rounds_total_score", table_name="game_rounds")
    op.drop_column("game_rounds", "total_score")
