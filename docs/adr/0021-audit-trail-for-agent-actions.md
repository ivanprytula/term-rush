# ADR-0021: Audit-trail layer for agent actions

- **Status:** Accepted
- **Date:** 2026-09-28
- **Related:** ADR-0004 (review queue - the human-approval gate this audit
  trail records), ADR-0011 (Kafka event log - `EventEnvelope` is extended,
  not replaced), ADR-0019 (agent orchestration - the primary new source of
  events this ADR needs to capture), ADR-0020 (MCP server - tool calls
  from an external MCP client are also in scope)

## Context

Cluster A's postings (regulated-domain agentic RAG - AFC/KYC, asset
management) consistently ask for one thing this project has never
written down explicitly: a record of **who or what did a thing, on what
input, with what outcome, and why** - the compliance meaning of "audit
trail." Today that information exists, but scattered and partial:

- `ReviewCandidate` (`content_service/domain/review.py`) already carries
  `source_type`, `source_file`, `confidence`, and a `status` transition
  (PENDING -> APPROVED/REJECTED) - this is provenance and a decision
  record, but only for the term-review workflow, and only the *current*
  status is stored, not the history of who moved it there or when.
- `EventEnvelope` (`libs/core/src/termrush_core/events.py`, ADR-0011)
  already carries `event_id`, `event_type`, `payload`, `occurred_at`,
  `schema_version` - published for `AnswerGraded` and `TermPublished`
  today. This is most of an audit record's shape, already flowing through
  Kafka, already durable. It has no `actor` field, and nothing consumes
  these events into a queryable, append-only store - they're notifications
  for cache invalidation and stats, not a compliance log.
- `logging.py`'s structured JSON logs carry `trace_id`/`span_id` and a
  redacted-fields set - real observability, but logs are for debugging,
  not for answering "show me every action this agent took on candidate
  #482" months later. Log retention and a compliance audit trail are
  different requirements with different guarantees, even when today's
  code doesn't distinguish them.

ADR-0019 adds a LangGraph agent that retrieves, drafts, and critiques
without a human in the loop until the review-queue interrupt. ADR-0020
adds an MCP surface external clients can call directly. Both are new
*sources* of actions that need a "who/what/why" answer if either pillar's
compliance framing is going to survive a follow-up question in an
interview.

## Decision

**Extend `EventEnvelope` with an `actor` field, and add one new consumer
that persists every event onto an append-only `agent_audit_log` table.
No new event-publishing infrastructure - existing publish call sites
gain one new field, and a new consumer subscribes to the same topics.**

- **`actor` field on `EventEnvelope`:** a small discriminated shape -
  `{kind: "human" | "agent" | "system", id: str}`. A human approving a
  review candidate is `{kind: "human", id: <user id, once ADR-0014
  lands>}`; the LangGraph agent drafting a candidate is `{kind: "agent",
  id: "agentic-review-candidates-v1"}` (a version-carrying string, so a
  later prompt/graph revision is distinguishable in the log from an
  earlier one); the Kafka consumer invalidating a cache on `TermPublished`
  is `{kind: "system", id: "term-cache-invalidator"}`. Every existing
  publish call site (`AnswerGraded`, `TermPublished`) is updated to set
  this field - a small, mechanical change, not a redesign.
- **New event types**, published at the points ADR-0019/0020 introduce:
  `AgentToolInvoked` (payload: tool name, arguments, calling agent id -
  every MCP tool call and every LangGraph tool-node execution),
  `AgentDraftSubmitted` (a candidate entering the review queue via an
  agent actor, cross-referencing `ReviewCandidate.id`), and the existing
  `ReviewCandidate` approve/reject transitions gain their own publish
  call (today they mutate a row and fire `TermPublished` on approval only
  - rejection currently publishes nothing, which is itself a gap this
  ADR closes).
- **New consumer, `agent_audit_log` table:** one append-only table
  (`event_id` primary key, `event_type`, `actor_kind`, `actor_id`,
  `payload` JSONB, `occurred_at`, `schema_version`), written by a Kafka
  consumer that subscribes to every audit-relevant topic and inserts,
  never updates or deletes. This is the same consumer shape
  `answer_graded_stats` already uses (ADR-0011's TaskGroup-supervised
  consumer, bounded by `asyncio.timeout` per write) - a fourth consumer
  in an already-proven pattern, not new consumer infrastructure.
- **Query surface:** a read-only `GET /audit-log?actor_id=&event_type=&since=`
  endpoint, following the same Annotated-dependency FastAPI convention as
  every other router. Exposed read-only via MCP (ADR-0020) alongside the
  other read-only tools - "let me see what you did" is itself a
  reasonable agent-facing capability, and it's inherently safe (an
  append-only log has no mutating operation to gate).

### Why extend the event log, not a separate audit service

A dedicated audit service (its own datastore, its own write path) is the
same mistake ADR-0012 already argues against for vector databases at this
project's scale: a second piece of infrastructure to operate when the
first one (Kafka + Postgres, both already running) does the job. The
event log already carries almost the right shape; the gap is one field
and one consumer, not a new system.

## Consequences

**Good:**

- Closes a real, specifically-named gap (compliance audit trail) with a
  small extension to infrastructure that already exists and is already
  tested (ADR-0011's consumer pattern), rather than a new subsystem
- `actor.id` carrying a version string for agent actors means a prompt or
  graph-structure change is distinguishable in historical queries -
  "which version of the agent approved this" is answerable, which matters
  the moment ADR-0019's graph changes for the first time
- Rejection finally publishes an event (a real gap the review-queue code
  has today, independent of this ADR's agentic framing) - fixed as a
  side effect of making the log complete

**Bad:**

- `agent_audit_log` grows unboundedly by design (append-only, no
  deletion) - retention policy is explicitly out of scope for this ADR
  and needs its own decision before this reaches anything resembling
  real regulated-domain use
- A fourth Kafka consumer is a fourth thing to reason about under
  ADR-0011's TaskGroup supervision - not a new pattern, but not free
  either
- `actor.id` for a human is a real identity only once ADR-0014's auth
  ships; until then it's a placeholder string, and this ADR's compliance
  framing is honest only up to that caveat

## Alternatives considered

**Log-only (structured JSON logs, no separate table).** Rejected: logs
are typically retained on a rolling window and aren't optimized for
"every action on entity X across all time" queries the way an indexed
table is - conflating debugging logs with a compliance record is the
exact category error the Context section flags.

**A dedicated audit-log microservice.** Rejected per the "why extend, not
build" reasoning above - no volume or isolation justification exists yet,
matching this project's existing bar (ADR-0007: two services is enough to
demonstrate distributed concerns; a third here would be theatre without a
concrete driver).

**Store audit state as extra columns on each domain table** (e.g., an
`approved_by` column on `ReviewCandidate`) instead of a separate event-
sourced log. Rejected: this answers "what is the current state" but not
"what happened, in what order, by whom" - the review-queue's own status
field already shows this limitation today (current status only, no
history), which is the specific hole this ADR is closing.

## When I would change this

- If `agent_audit_log` query volume or size becomes a real operational
  concern, that's the trigger to evaluate a retention/archival policy -
  not a reason to abandon the append-only design.
- If a regulated-domain requirement surfaces that needs cryptographic
  tamper-evidence (hash-chaining audit records), that's an addition to
  this table's write path, not a different architecture.
- If audit queries need to join across services in ways a single
  Postgres table can't support cleanly (e.g., once a third service
  exists), revisit whether the audit log needs to move to its own
  service - the "two services is enough" reasoning above is explicitly
  about *today's* count, not a permanent ceiling.
