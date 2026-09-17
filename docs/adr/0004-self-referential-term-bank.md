# ADR-0004: The term bank is mined from this repository

- **Status:** Accepted
- **Date:** 2026-09-17
- **Related:** ADR-0003 (principles before frameworks), ADR-0002 (grading strategy)

## Context

The prototype shipped 24 hand-typed terms: `CPU`, `RAM`, `TCP/IP`. Generic CS trivia.
Two problems with continuing that way.

**Learning problem.** Terms disconnected from anything you are doing decay fast. You
memorize "UoW = Unit of Work", it survives a week, it goes. There is no anchor.

**Content problem.** A hand-typed term bank does not scale past what one person will
sit down and write, and writing 300 knowledge objects by hand is the least interesting
work in the project.

Meanwhile this repository is *already* a dense, growing corpus of exactly the
vocabulary worth learning — ADR headings, docstrings, dependency manifests, config
keys. It is a glossary that writes itself as a side effect of building.

## Decision

**The term bank is generated from this repository, by a pipeline, with human review.**

`UoW` is not trivia. It is `SqlAlchemyUnitOfWork` in `infrastructure/persistence/`,
which you wrote. `Idempotency` is the consumer test you debugged. `OTel` is the trace
you stared at. The game teaches the stack it is built on, and the bank grows as the
project does.

### Why this is the right shape for the project

1. **Learning anchor.** Every term maps to code you can open. Spaced repetition on
   concepts you have hands on is categorically more durable than on flashcards.
2. **It is a real data pipeline.** Heterogeneous sources with genuinely different
   reliability — not a `json.load` dressed up as ETL. See below.
3. **The README pitch writes itself:** *the game teaches the stack it is built on, and
   the term bank is generated from the repo.*
4. **It compounds.** Phase 3 adds Kafka → `Idempotency`, `Outbox`, `Consumer Group`,
   `Replay` appear in the bank automatically. The corpus and the project grow together.

### Extraction sources, by confidence

The heterogeneity is the point. A pipeline over one clean source is not interesting;
a pipeline that must reconcile three sources of differing trust is.

| Source | Confidence | Yields | Failure mode |
| --- | --- | --- | --- |
| Dependency manifests (`pyproject.toml`, `package.json`, `*.tf`) | **High** — structured, machine-parseable | `fastapi`, `sqlalchemy`, `pgvector` | Names a tool, not a concept |
| ADR + doc headings | **Medium** — curated prose, human-written | `Idempotency`, `Backpressure`, `Outbox` | Heading text is not always a term |
| Docstrings + class/Protocol names | **Medium** | `Grader`, `AnswerEvaluator`, `UnitOfWork` | Project-local jargon, not industry vocabulary |
| Code identifiers, comments | **Low** — noisy | everything and nothing | Mostly junk; needs aggressive filtering |
| Config keys, env vars, k8s manifests | **Medium** | `HPA`, `PDB`, `readinessProbe` | Vendor-specific |

Confidence is carried through the pipeline as a first-class field and drives whether a
candidate is auto-promoted, queued for review, or dropped.

### Pipeline stages

```text
 extract          enrich            validate         load           serve
 ────────         ──────            ────────         ────           ─────
 repo sources     LLM drafts        schema +         warehouse      game API
 → candidates     knowledge         quality          + review       + MCP
   w/ provenance  object            contracts        queue            server
```

- **Extract** — deterministic parsers per source. No LLM. Emits candidates with
  provenance (file, line, source type, confidence). Fully testable, no API key needed.
- **Enrich** — LLM drafts the knowledge object: definitions, examples, prerequisites,
  related terms, common mistakes. Grounded by RAG over the repo itself so the example
  cites *this* codebase, not a generic one.
- **Validate** — schema conformance plus data-quality contracts (see below). Failures
  block promotion; they do not silently degrade the bank.
- **Load** — warehouse tables + the operational term store.
- **Review** — everything LLM-authored lands in a queue for human approval. **An agent
  writing to the live term bank unreviewed is a liability**, and the review gate is the
  senior decision, not a limitation.

### Data quality contracts

Non-negotiable, enforced in the pipeline and failing CI:

- `expansion` is non-empty and differs from `term`
- at least one definition, ≥40 chars for anything Boss-eligible
- `prerequisites` form a **DAG** — a term cannot transitively require itself
- `related` references resolve to terms that exist
- no duplicate terms after normalization (`TCP/IP` and `TCP IP` are one term)
- `difficulty` distribution stays sane — an all-EXPERT bank is a broken enricher
- provenance is present on every row; a term with no source is a bug

The DAG check is the interesting one: prerequisite cycles are how a learning path
silently becomes unsatisfiable, and it is a genuine graph problem rather than a
null-check.

## Consequences

**Good:**

- Terms are anchored to code you wrote. Learning actually sticks.
- A legitimately interesting pipeline: multi-source, differing trust, LLM in the
  middle, quality gates, human review.
- Self-growing corpus. Phase 3's infrastructure vocabulary arrives free.
- Full lineage story: every term traces to a file and line.

**Bad:**

- Bootstrapping problem: early repo yields ~30 terms. Mitigated by seeding the
  prototype's 24 and letting the bank grow with the project — which is the point.
- Repo-mined vocabulary skews to what this project uses. It will never teach you
  frontend animation or embedded systems. Accepted: the goal is depth in *this* stack.
- LLM enrichment costs money and needs review time. Bounded by batching, caching, and
  the fact that enrichment runs once per term, not per play.
- Extraction quality on the low-confidence sources will be poor at first. That is why
  confidence is a field and review is a gate.

## Alternatives considered

**Hand-curated list of ~150 terms.** Guaranteed relevant, zero pipeline. Rejected: it
deletes the most interesting engineering in the proposal, and it does not grow.

**Extract with no LLM enrichment.** Deterministic and free. Rejected: hand-authoring
hundreds of definitions, examples and prerequisite graphs is the bulk of the work and
the least rewarding part.

**Mine public sources (Wikipedia, awesome-lists) instead.** Bigger corpus, no personal
anchor — straight back to generic trivia, which is the problem being solved.

## When I would change this

- If repo-mined vocabulary plateaus below ~200 terms and the game needs more variety,
  add a second extractor over a curated external corpus — keeping provenance so
  repo-anchored terms can still be prioritized in scheduling.
- If review load becomes the bottleneck, auto-promote high-confidence candidates
  (dependency manifests) and reserve review for medium and low.
- If the LLM enricher proves unreliable on prerequisites specifically, that field goes
  back to hand-authoring while the rest stays generated.
