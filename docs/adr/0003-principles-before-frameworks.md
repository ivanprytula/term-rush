# ADR-0003: Evergreen principles first, frameworks second

- **Status:** Accepted
- **Date:** 2026-09-17
- **Supersedes nothing, but governs:** every subsequent ADR

## Context

The temptation in a portfolio project is to lead with tool names, because tool names
are what job descriptions list and what keyword filters match. "Built with FastAPI,
Kafka, Kubernetes, pgvector."

That framing ages badly in two directions. Within three years half those names will
have shifted. And in an interview it invites the only question it cannot survive:
*why that one?* A candidate who can only name tools is indistinguishable from a
candidate who followed a tutorial.

The durable skill is almost never the library. It is the problem the library solves,
which existed before the library and will outlive it:

| Evergreen                              | Current expression here               | Replaceable by                |
| -------------------------------------- | ------------------------------------- | ----------------------------- |
| Dependency inversion at I/O boundaries | `Protocol` ports + SQLAlchemy adapter | any ORM, or raw SQL           |
| Server state ≠ client state            | TanStack Query + Zustand              | SWR, Redux, signals           |
| Backpressure and bounded concurrency   | `asyncio.Semaphore`                   | any runtime's equivalent      |
| At-least-once delivery + idempotency   | Kafka + outbox                        | SQS, Pub/Sub, NATS            |
| Retrieval quality is measurable        | pgvector + recall@k                   | any vector store              |
| Spaced repetition scheduling           | FSRS                                  | SM-2, Leitner, Anki's variant |
| Open/Closed extension seam             | abstain-protocol grader chain         | any plugin pattern            |

## Decision

**Principles live in `domain/`. Frameworks live in `infrastructure/`. The boundary is
machine-enforced, not merely intended.**

Three concrete rules:

### 1. The domain layer imports no framework

Enforced by import-linter contract `Domain is framework-free`, which forbids
`fastapi`, `sqlalchemy`, `redis` and `celery` from `game_service.domain`. This is
verified negatively: injecting `import sqlalchemy` into `domain/term.py` breaks CI,
and that was tested before the rule was trusted.

The grader chain, the FSRS scheduler, the rubric weights, the term knowledge object —
all of it is plain Python that would survive swapping every framework in the stack.

### 2. Every framework choice is a documented *trade*, not a default

An ADR that says "we use X because X is popular" is not an ADR. Each one must name
what was given up. Where the honest answer is "any of these three would work, I picked
one and here's the tiebreaker", say exactly that — false precision is worse than an
admitted coin-flip.

### 3. Documentation leads with the problem

Every doc and ADR opens with the problem in framework-neutral terms, then names the
tool. `docs/skills-map.md` is organized by capability (API design, concurrency,
retrieval quality), never by vendor.

## Consequences

**Good:**

- The interview conversation moves to judgment, where the signal is.
- Framework swaps stay local. Replacing SQLAlchemy touches `infrastructure/persistence/`
  and nothing else — which is the claim ADR-0001's "reversibility" rests on.
- Future-me reads intent rather than API calls.

**Bad:**

- Ports and adapters cost indirection. A CRUD endpoint calling the repository directly
  would be shorter. This is accepted *only* at genuine I/O boundaries — not as a
  blanket policy, and not "for testability" where the code is already testable.
- Risk of principle-worship: inventing an abstraction for a thing that has exactly one
  implementation and always will. Guard: an interface appears when the second
  implementation does, or when the boundary is a real I/O edge, never speculatively.

## When I would change this

If the indirection ever obscures more than it protects — if a reader has to traverse
three files to find where a query runs — the abstraction has stopped paying and should
collapse back into the concrete. Simplicity outranks purity; this ADR is a default,
not a religion.
