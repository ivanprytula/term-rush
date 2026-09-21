"""rename sessions table to game_rounds

Revision ID: b2a7f5e9c3d1
Revises: e85d3e4c9ed1
Create Date: 2026-09-21 12:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2a7f5e9c3d1'
down_revision: Union[str, Sequence[str], None] = 'e85d3e4c9ed1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("sessions", "game_rounds")


def downgrade() -> None:
    """Downgrade schema."""
    op.rename_table("game_rounds", "sessions")
