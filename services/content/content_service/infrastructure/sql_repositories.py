"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from content_service.application.ports import DocumentChunkRepository
from content_service.application.ports import ReviewQueueRepository
from content_service.application.ports import TermRepository
from content_service.domain.document_chunk import DocumentChunk
from content_service.domain.review import ReviewCandidate
from content_service.domain.review import ReviewStatus
from content_service.domain.term import Term
from content_service.infrastructure.database import DocumentChunkModel
from content_service.infrastructure.database import ReviewCandidateModel
from content_service.infrastructure.database import TermAliasModel
from content_service.infrastructure.database import TermCategoryModel
from content_service.infrastructure.database import TermCommonMistakeModel
from content_service.infrastructure.database import TermDefinitionModel
from content_service.infrastructure.database import TermExampleModel
from content_service.infrastructure.database import TermModel
from content_service.infrastructure.database import TermPrerequisiteModel
from content_service.infrastructure.database import TermRelatedModel

_CHILD_RELATIONSHIPS = (
    "definitions",
    "aliases",
    "examples",
    "categories",
    "prerequisites",
    "related",
    "common_mistakes",
)


def _eager_load(stmt):
    """Attach a selectinload for every child relationship, so a Term never
    triggers a lazy-load query per list field (N+1 across 7 tables).
    """
    for name in _CHILD_RELATIONSHIPS:
        stmt = stmt.options(selectinload(getattr(TermModel, name)))
    return stmt


def _to_domain(model: TermModel) -> Term:
    """Assemble a domain Term from a TermModel and its (already-loaded)
    child rows, each ordered by its own `position` column.
    """
    return Term(
        id=model.id,
        term=model.term,
        expansion=model.expansion,
        difficulty=model.difficulty,
        definitions=tuple(d.value for d in model.definitions),
        aliases=tuple(a.value for a in model.aliases),
        examples=tuple(e.value for e in model.examples),
        categories=tuple({"slug": c.slug} for c in model.categories),
        prerequisites=tuple(p.requires_term_id for p in model.prerequisites),
        related=tuple(r.related_term_id for r in model.related),
        common_mistakes=tuple(m.value for m in model.common_mistakes),
    )


class SQLTermRepository(TermRepository):
    """Query and persist terms in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_id(self, term_id: str) -> Term | None:
        """Fetch a term by ID from the database."""
        stmt = _eager_load(select(TermModel).where(TermModel.id == term_id))
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return _to_domain(model) if model else None

    async def random(
        self,
        excluded_ids: frozenset[str] = frozenset(),
        category: str | None = None,
        min_difficulty: int | None = None,
        require_examples: bool = False,
        min_definition_length: int | None = None,
    ) -> Term | None:
        """Fetch a random term, avoiding excluded_ids where possible, scoped
        to category and/or content-property constraints if given.

        Filters apply against real columns and joined child tables now
        that the schema is normalized (ADR-0012) — category and difficulty
        are indexable joins/predicates instead of jsonb operations.

        Falls back to the full matching set once excluded_ids covers every
        matching term (a round that has shown everything in its scope
        should repeat, not fail) — every other filter still applies on the
        fallback, so an exhausted Boss round never falls back to an
        ineligible term.
        """
        stmt = select(TermModel)
        if category is not None:
            stmt = stmt.join(TermModel.categories).where(
                TermCategoryModel.slug == category
            )
        if min_difficulty is not None:
            stmt = stmt.where(TermModel.difficulty >= min_difficulty)
        if require_examples:
            stmt = stmt.join(TermModel.examples)
        if min_definition_length is not None:
            # First definition is the primary one (Term.primary_definition);
            # position 0 within the join picks it out per term.
            stmt = stmt.join(TermModel.definitions).where(
                TermDefinitionModel.position == 0,
                func.length(TermDefinitionModel.value) >= min_definition_length,
            )
        if excluded_ids:
            stmt = stmt.where(TermModel.id.not_in(excluded_ids))
        stmt = _eager_load(stmt.order_by(func.random()).limit(1))

        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if not model and excluded_ids:
            return await self.random(
                category=category,
                min_difficulty=min_difficulty,
                require_examples=require_examples,
                min_definition_length=min_definition_length,
            )
        return _to_domain(model) if model else None

    async def categories(self) -> tuple[str, ...]:
        """List every category slug present in the term bank."""
        stmt = select(func.distinct(TermCategoryModel.slug))
        result = await self.session.execute(stmt)
        return tuple(sorted(result.scalars().all()))

    async def all_ids(self) -> tuple[str, ...]:
        """Every term id, sorted in SQL so an unstable order can't
        silently change a Daily 20 puzzle."""
        stmt = select(TermModel.id).order_by(TermModel.id)
        result = await self.session.execute(stmt)
        return tuple(result.scalars().all())

    async def upsert(self, term: Term) -> None:
        """Create the term, or replace it if the ID already exists.

        Child rows are delete + reinsert on every upsert rather than
        diffed: Term is frozen and republished as a whole (its own
        docstring — "never mutated in place"), so there is no partial-list
        update to preserve, and nothing references a child row by its own
        identity today.
        """
        stmt = insert(TermModel).values(
            id=term.id,
            term=term.term,
            expansion=term.expansion,
            difficulty=int(term.difficulty),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "term": stmt.excluded.term,
                "expansion": stmt.excluded.expansion,
                "difficulty": stmt.excluded.difficulty,
            },
        )
        await self.session.execute(stmt)

        await self._replace_children(
            TermDefinitionModel, term.id, "value", term.definitions
        )
        await self._replace_children(TermAliasModel, term.id, "value", term.aliases)
        await self._replace_children(TermExampleModel, term.id, "value", term.examples)
        await self._replace_children(
            TermCategoryModel,
            term.id,
            "slug",
            tuple(c.slug for c in term.categories),
        )
        await self._replace_children(
            TermPrerequisiteModel, term.id, "requires_term_id", term.prerequisites
        )
        await self._replace_children(
            TermRelatedModel, term.id, "related_term_id", term.related
        )
        await self._replace_children(
            TermCommonMistakeModel, term.id, "value", term.common_mistakes
        )

    async def _replace_children(
        self, model, term_id: str, value_column: str, values: tuple[str, ...]
    ) -> None:
        """Delete every existing child row for term_id, then bulk-insert
        the incoming values in order (position = list index).
        """
        await self.session.execute(delete(model).where(model.term_id == term_id))
        if not values:
            return
        rows = [
            {"term_id": term_id, "position": position, value_column: value}
            for position, value in enumerate(values)
        ]
        await self.session.execute(insert(model), rows)


def _candidate_to_domain(model: ReviewCandidateModel) -> ReviewCandidate:
    return ReviewCandidate(
        id=model.id,
        term=Term.model_validate_json(model.term_data),
        source_type=model.source_type,
        source_file=model.source_file,
        confidence=model.confidence,
        status=ReviewStatus(model.status),
    )


class SQLReviewQueueRepository(ReviewQueueRepository):
    """Query and persist review candidates in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, candidate: ReviewCandidate) -> ReviewCandidate:
        model = ReviewCandidateModel(
            term_data=candidate.term.model_dump_json(),
            source_type=candidate.source_type,
            source_file=candidate.source_file,
            confidence=candidate.confidence,
            status=candidate.status.value,
        )
        self.session.add(model)
        await self.session.flush()  # assigns model.id via the DB sequence
        return _candidate_to_domain(model)

    async def by_id(self, candidate_id: int) -> ReviewCandidate | None:
        model = await self.session.get(ReviewCandidateModel, candidate_id)
        return _candidate_to_domain(model) if model else None

    async def list_by_status(self, status: ReviewStatus) -> tuple[ReviewCandidate, ...]:
        stmt = (
            select(ReviewCandidateModel)
            .where(ReviewCandidateModel.status == status.value)
            .order_by(ReviewCandidateModel.id)
        )
        result = await self.session.execute(stmt)
        return tuple(_candidate_to_domain(m) for m in result.scalars().all())

    async def set_status(self, candidate_id: int, status: ReviewStatus) -> None:
        model = await self.session.get(ReviewCandidateModel, candidate_id)
        if model is None:
            return
        model.status = status.value


def _chunk_to_domain(model: DocumentChunkModel) -> DocumentChunk:
    return DocumentChunk(
        id=model.id,
        text=model.text,
        source_file=model.source_file,
        chunk_index=model.chunk_index,
        char_start=model.char_start,
        char_end=model.char_end,
    )


class SQLDocumentChunkRepository(DocumentChunkRepository):
    """Query and persist document chunks in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_batch(
        self, chunks: tuple[DocumentChunk, ...]
    ) -> tuple[DocumentChunk, ...]:
        models = [
            DocumentChunkModel(
                text=chunk.text,
                source_file=chunk.source_file,
                chunk_index=chunk.chunk_index,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
            for chunk in chunks
        ]
        self.session.add_all(models)
        await self.session.flush()  # assigns model.id via the DB sequence
        return tuple(_chunk_to_domain(m) for m in models)

    async def by_source_file(self, source_file: str) -> tuple[DocumentChunk, ...]:
        stmt = (
            select(DocumentChunkModel)
            .where(DocumentChunkModel.source_file == source_file)
            .order_by(DocumentChunkModel.chunk_index)
        )
        result = await self.session.execute(stmt)
        return tuple(_chunk_to_domain(m) for m in result.scalars().all())

    async def delete_by_source_file(self, source_file: str) -> None:
        stmt = delete(DocumentChunkModel).where(
            DocumentChunkModel.source_file == source_file
        )
        await self.session.execute(stmt)
