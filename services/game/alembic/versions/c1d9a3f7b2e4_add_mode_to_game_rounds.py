"""add mode to game_rounds

Revision ID: c1d9a3f7b2e4
Revises: a846b8bd7b58
Create Date: 2026-09-22 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d9a3f7b2e4'
down_revision: Union[str, Sequence[str], None] = 'a846b8bd7b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("game_rounds", sa.Column("mode", sa.String(16), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, data FROM game_rounds")).fetchall()
    for round_id, data in rows:
        mode = json.loads(data).get("mode", "classic")
        conn.execute(
            sa.text("UPDATE game_rounds SET mode = :mode WHERE id = :id"),
            {"mode": mode, "id": round_id},
        )

    op.alter_column("game_rounds", "mode", nullable=False)
    op.create_index(
        "ix_game_rounds_mode_total_score",
        "game_rounds",
        ["mode", sa.text("total_score DESC")],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_game_rounds_mode_total_score", table_name="game_rounds")
    op.drop_column("game_rounds", "mode")
