"""normalize term list fields into child tables

Revision ID: ee11c9066b2e
Revises: 4344fb1036bd
Create Date: 2026-09-23 23:02:42.968688

Expand-contract: new columns/tables are added nullable, backfilled from the
existing `data` JSON blob, then tightened/dropped. Safe to run against a
terms table that already has rows.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee11c9066b2e'
down_revision: Union[str, Sequence[str], None] = '4344fb1036bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('term_aliases',
    sa.Column('value', sa.String(length=64), nullable=False),
    sa.Column('term_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], name=op.f('fk_term_aliases_term_id_terms'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'position', name=op.f('pk_term_aliases'))
    )
    op.create_table('term_categories',
    sa.Column('slug', sa.String(length=32), nullable=False),
    sa.Column('term_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], name=op.f('fk_term_categories_term_id_terms'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'position', name=op.f('pk_term_categories')),
    sa.UniqueConstraint('term_id', 'slug', name='uq_term_categories_term_id_slug')
    )
    op.create_table('term_common_mistakes',
    sa.Column('value', sa.String(length=1024), nullable=False),
    sa.Column('term_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], name=op.f('fk_term_common_mistakes_term_id_terms'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'position', name=op.f('pk_term_common_mistakes'))
    )
    op.create_table('term_definitions',
    sa.Column('value', sa.String(length=1024), nullable=False),
    sa.Column('term_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], name=op.f('fk_term_definitions_term_id_terms'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'position', name=op.f('pk_term_definitions'))
    )
    op.create_table('term_examples',
    sa.Column('value', sa.String(length=1024), nullable=False),
    sa.Column('term_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], name=op.f('fk_term_examples_term_id_terms'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'position', name=op.f('pk_term_examples'))
    )
    op.create_table('term_prerequisites',
    sa.Column('requires_term_id', sa.String(length=64), nullable=False),
    sa.Column('term_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], name=op.f('fk_term_prerequisites_term_id_terms'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'position', name=op.f('pk_term_prerequisites'))
    )
    op.create_table('term_related',
    sa.Column('related_term_id', sa.String(length=64), nullable=False),
    sa.Column('term_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], name=op.f('fk_term_related_term_id_terms'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'position', name=op.f('pk_term_related'))
    )

    # New scalar columns start nullable so existing rows aren't rejected
    # before the backfill below populates them.
    op.add_column('terms', sa.Column('term', sa.String(length=64), nullable=True))
    op.add_column('terms', sa.Column('expansion', sa.String(length=256), nullable=True))
    op.add_column('terms', sa.Column('difficulty', sa.Integer(), nullable=True))

    _backfill_from_json_blob()

    op.alter_column('terms', 'term', nullable=False)
    op.alter_column('terms', 'expansion', nullable=False)
    op.alter_column('terms', 'difficulty', nullable=False)
    op.drop_column('terms', 'data')


def _backfill_from_json_blob() -> None:
    """Parse each row's `data` JSON blob and populate the new columns and
    child tables. Runs once, inside this migration's transaction — no
    ORM models involved, so later domain changes can't silently break an
    already-applied migration.
    """
    connection = op.get_bind()
    terms = connection.execute(sa.text("SELECT id, data FROM terms")).fetchall()

    for term_id, raw in terms:
        data = json.loads(raw)
        connection.execute(
            sa.text(
                "UPDATE terms SET term = :term, expansion = :expansion, "
                "difficulty = :difficulty WHERE id = :id"
            ),
            {
                "term": data["term"],
                "expansion": data["expansion"],
                "difficulty": int(data["difficulty"]),
                "id": term_id,
            },
        )
        _insert_child_rows(connection, "term_definitions", term_id, "value", data["definitions"])
        _insert_child_rows(connection, "term_aliases", term_id, "value", data.get("aliases", []))
        _insert_child_rows(connection, "term_examples", term_id, "value", data.get("examples", []))
        _insert_child_rows(
            connection,
            "term_categories",
            term_id,
            "slug",
            [c["slug"] for c in data.get("categories", [])],
        )
        _insert_child_rows(
            connection,
            "term_prerequisites",
            term_id,
            "requires_term_id",
            data.get("prerequisites", []),
        )
        _insert_child_rows(
            connection, "term_related", term_id, "related_term_id", data.get("related", [])
        )
        _insert_child_rows(
            connection,
            "term_common_mistakes",
            term_id,
            "value",
            data.get("common_mistakes", []),
        )


def _insert_child_rows(
    connection, table: str, term_id: str, value_column: str, values: list[str]
) -> None:
    for position, value in enumerate(values):
        connection.execute(
            sa.text(
                f"INSERT INTO {table} (term_id, position, {value_column}) "
                f"VALUES (:term_id, :position, :value)"
            ),
            {"term_id": term_id, "position": position, "value": value},
        )


def downgrade() -> None:
    """Downgrade schema.

    Reconstructs `data` by re-serializing the normalized rows back into
    the original blob shape, so downgrade round-trips real data too.
    """
    op.add_column('terms', sa.Column('data', sa.VARCHAR(length=4096), autoincrement=False, nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, term, expansion, difficulty FROM terms")
    ).fetchall()
    for term_id, term, expansion, difficulty in rows:
        payload = {
            "id": term_id,
            "term": term,
            "expansion": expansion,
            "difficulty": difficulty,
            "definitions": _select_ordered(connection, "term_definitions", term_id, "value"),
            "aliases": _select_ordered(connection, "term_aliases", term_id, "value"),
            "examples": _select_ordered(connection, "term_examples", term_id, "value"),
            "categories": [
                {"slug": s}
                for s in _select_ordered(connection, "term_categories", term_id, "slug")
            ],
            "prerequisites": _select_ordered(
                connection, "term_prerequisites", term_id, "requires_term_id"
            ),
            "related": _select_ordered(connection, "term_related", term_id, "related_term_id"),
            "common_mistakes": _select_ordered(
                connection, "term_common_mistakes", term_id, "value"
            ),
        }
        connection.execute(
            sa.text("UPDATE terms SET data = :data WHERE id = :id"),
            {"data": json.dumps(payload), "id": term_id},
        )

    op.alter_column('terms', 'data', nullable=False)
    op.drop_column('terms', 'difficulty')
    op.drop_column('terms', 'expansion')
    op.drop_column('terms', 'term')
    op.drop_table('term_related')
    op.drop_table('term_prerequisites')
    op.drop_table('term_examples')
    op.drop_table('term_definitions')
    op.drop_table('term_common_mistakes')
    op.drop_table('term_categories')
    op.drop_table('term_aliases')


def _select_ordered(connection, table: str, term_id: str, value_column: str) -> list[str]:
    rows = connection.execute(
        sa.text(
            f"SELECT {value_column} FROM {table} WHERE term_id = :term_id "
            f"ORDER BY position"
        ),
        {"term_id": term_id},
    ).fetchall()
    return [r[0] for r in rows]
