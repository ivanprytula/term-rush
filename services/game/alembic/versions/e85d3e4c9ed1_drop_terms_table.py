"""drop terms table

Revision ID: e85d3e4c9ed1
Revises: fa6d4bb17eb4
Create Date: 2026-09-20 00:00:00.000000

Terms moved to content-service (ADR-0009): game-service now fetches term
knowledge over gRPC instead of owning a local copy. content-service's own
migration history seeded the equivalent table before this one drops it here
— see services/content/alembic/versions/4344fb1036bd_initial_schema_terms_table.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e85d3e4c9ed1'
down_revision: Union[str, Sequence[str], None] = 'fa6d4bb17eb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table("terms")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "terms",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("data", sa.String(4096), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
