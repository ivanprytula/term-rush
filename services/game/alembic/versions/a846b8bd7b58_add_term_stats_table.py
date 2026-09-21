"""add term_stats table

Revision ID: a846b8bd7b58
Revises: f32b4155291c
Create Date: 2026-09-21 22:52:08.735479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a846b8bd7b58'
down_revision: Union[str, Sequence[str], None] = 'f32b4155291c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "term_stats",
        sa.Column("term_id", sa.String(length=64), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("partial_count", sa.Integer(), nullable=False),
        sa.Column("incorrect_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("term_id", name=op.f("pk_term_stats")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("term_stats")
