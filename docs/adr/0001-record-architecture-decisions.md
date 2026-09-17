# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-09-17
- **Deciders:** Solo project

## Context

Term Rush v2 is deliberately built with more infrastructure than its problem size
demands — two services, three message brokers, two clouds, Kubernetes. The primary
audience is an interviewer, and the secondary audience is me in three months, having
forgotten every reason for every choice.

Without written rationale, that over-engineering reads as cargo-culting. With it, it
reads as judgment. The difference between a mid-level and a senior engineer is not
which technologies they can wire together; it is whether they can say why, and when
they would not.

## Decision

Every significant decision gets an ADR in `docs/adr/`, in MADR-ish format, numbered
sequentially and never deleted — superseded ADRs are marked `Superseded by ADR-NNNN`
and left in place, because the reasoning that turned out wrong is as instructive as
the reasoning that held.

An ADR is warranted when a choice is:

- expensive to reverse (datastore, messaging topology, deployment target), or
- non-obvious to a reader (why Kafka *and* RabbitMQ), or
- deliberately suboptimal for a documented reason (why the fuzzy matcher is naive).

Each ADR must include a **"When I would change this"** section. An ADR without a
stated reversal condition is an advertisement, not a decision record.

## Consequences

**Good:**
- The repo is self-explaining to a reviewer who has 15 minutes.
- Future-me can re-enter the project without re-deriving context.
- The negative ADRs ("why we did NOT use X in production") are the strongest signal
  in the repo, because they demonstrate restraint rather than enthusiasm.

**Bad:**
- Writing overhead on every meaningful change.
- Risk of ADRs drifting from the code. Mitigated by keeping them short and linking
  them from the code they describe (see the docstring references in
  `domain/evaluation/graders.py`).

## When I would change this

If this project ever gained collaborators, ADRs would need a lightweight review step
before acceptance. As a solo project, self-acceptance is fine.
