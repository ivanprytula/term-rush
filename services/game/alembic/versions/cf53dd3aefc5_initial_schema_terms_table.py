"""Initial schema: terms table

Revision ID: cf53dd3aefc5
Revises:
Create Date: 2026-09-18 01:01:02.820424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf53dd3aefc5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "terms",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("data", sa.String(4096), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("terms")
