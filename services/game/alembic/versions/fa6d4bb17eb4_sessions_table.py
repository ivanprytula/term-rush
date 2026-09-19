"""sessions table

Revision ID: fa6d4bb17eb4
Revises: cf53dd3aefc5
Create Date: 2026-09-19 01:30:43.418795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa6d4bb17eb4'
down_revision: Union[str, Sequence[str], None] = 'cf53dd3aefc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("data", sa.String(65536), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("sessions")
