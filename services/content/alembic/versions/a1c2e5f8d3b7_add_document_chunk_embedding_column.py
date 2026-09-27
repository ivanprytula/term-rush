"""add document_chunks.embedding column (ADR-0012 Slice 2)

Revision ID: a1c2e5f8d3b7
Revises: 3c6f4f21ca8c
Create Date: 2026-09-27 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'a1c2e5f8d3b7'
down_revision: Union[str, Sequence[str], None] = '3c6f4f21ca8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 384  # sentence-transformers all-MiniLM-L6-v2; keep in sync
# with content_service.domain.constants.DOCUMENT_CHUNK_EMBEDDING_DIM


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document_chunks", "embedding")
    # Extension intentionally left installed — other tables/rows may still
    # depend on it, and dropping it is a separate, deliberate decision.
