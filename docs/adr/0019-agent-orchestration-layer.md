# ADR-0019: Agent orchestration layer (LangGraph, scoped to one new slice)

- **Status:** Accepted
- **Date:** 2026-09-28
- **Related:** ADR-0004 (extract/enrich/validate/load pipeline - stays
  unchanged, see below), ADR-0012 (pgvector/RAG corpus - becomes a tool
  this ADR's agent calls), ADR-0013 (prompt injection defense - the
  pattern this ADR's tool-input hardening follows)

## Context

Skills-map lists "Agentic workflows and tool use (MCP)" as `Tool-use loop
✅ P3`, pointing at the Dagster `enriched_candidates` asset
(`assets/enriched.py`). That code is real, tested, and uses forced
`tool_use` the same way `AnthropicJudgePort` does. It is not, however,
what the job postings driving this phase mean by "agentic" - `enrich()`
makes exactly one predetermined LLM call per candidate, with no branching
on what the model decides. The control flow is fixed Python; the LLM
never chooses which step runs next or which tool to reach for. Anthropic's
own distinction (*Building Effective Agents*) calls this a **workflow**:
predefined code paths orchestrating LLM calls. An **agent**, by contrast,
lets the model choose its own next action from environment feedback, in a
loop, until it decides it's done.

Every posting behind Cluster A (regulated-domain agentic RAG) names
LangGraph, CrewAI, or "agent orchestration" explicitly - not "an LLM call
inside a pipeline." That gap is real and unclaimed by any code in this
repo today. Closing it is this ADR's job.

### Candidates considered

**LangGraph.** Graph-based: nodes are steps, edges are transitions,
state is an explicit typed object threaded through the graph. Production
deployments (Klarna's customer-service assistant, AWS's market-
surveillance agent on Bedrock AgentCore, LinkedIn, Uber) consistently cite
the same three things: durable checkpointing (resume from the last
completed node after a crash, not from scratch), a human-in-the-loop
interrupt primitive (the graph halts and waits for approval before a
sensitive step), and per-node/per-edge error handling (retry policies,
conditional fallback edges) instead of one try/except around the whole
loop. Klarna's traces are inspected node-by-node in LangSmith - the graph
structure is also the observability structure, for free.
[Sources: AWS ML blog on the market-surveillance agent; multiple 2026
framework comparisons citing Klarna's production numbers.]

**CrewAI.** Role-based: agents are "employees" with job titles, delegating
tasks to each other. Fastest to a demo, weakest on the things this project
already treats as non-negotiable (ADR-0011, ADR-0013): comparisons
consistently flag no built-in observability equivalent to LangSmith, and
error handling that lives at the crew/task level rather than being
inspectable per step. That's a worse fit for a "compliance audit trail"
pillar than it looks on day one.

**Hand-rolled tool loop** (`while` loop calling `messages.create` with
`tools=`, feeding tool results back in). This is what `enrich()` already
approximates for a single non-branching call. Rolling it forward into a
real multi-step agent means re-implementing, by hand, the exact things
LangGraph ships as primitives: state checkpointing, cycle-termination
guards, per-step retry. Doing that badly (unbounded loop, no checkpoint,
no interrupt point) is a believable production failure mode - the kind of
mistake a JD screener is checking whether a candidate has already made and
learned from.

## Decision

**Add LangGraph as a new, additive Dagster asset chain feeding the review
queue. The existing extract -> enrich -> validate -> load pipeline
(ADR-0004) is untouched.**

Concretely, one new slice:

- **New asset: `agentic_review_candidates`.** A LangGraph graph with three
  node types: `retrieve` (calls the existing pgvector search from
  ADR-0012 as a tool), `draft` (the model proposes an `EnrichedTerm`,
  same Pydantic schema `enrich.py` already defines), `critique` (the model
  re-checks its own draft against the retrieved context and either accepts
  or loops back to `retrieve` with a refined query, bounded by a max-
  iteration count on the edge). This is the first place in the repo where
  the *model* - not fixed Python - decides whether another retrieval pass
  is needed.
- **Checkpointing**, via LangGraph's built-in checkpointer (SQLite locally,
  matching this repo's existing "one Postgres instance, no new
  infrastructure for infrastructure's sake" stance from ADR-0012 -
  Postgres-backed checkpointing if/when this leaves prototype).
- **Human-in-the-loop interrupt** before the graph's output reaches the
  review queue - reusing the existing `GET /review-queue` /
  `POST /review-queue/{id}/approve` / `POST /review-queue/{id}/reject`
  endpoints (ADR-0004), not a new approval mechanism or LangGraph's
  `interrupt()`/`Command` resume primitive: the graph's terminal node
  submits the draft as PENDING and the run ends there. Approval/rejection
  happens out-of-band, through the review-queue UI, on a different code
  path entirely - there is nothing to resume, since the queue's own
  PENDING state is the durable halt point.
- **Tool-input hardening**: any tool the graph exposes to the model
  (pgvector search, repo grep) gets the same treatment ADR-0013 already
  established for player answers - the model's tool-call arguments are
  untrusted input from the LLM's perspective just as a player's answer is,
  and get validated/escaped the same way before touching a real query.

### Why additive, not a replacement

`enriched_candidates` (ADR-0004) is deterministic, cheap, and correct for
its job: one candidate, one draft, no ambiguity about what "done" means.
An agent loop costs more tokens and more latency to solve a problem that
doesn't need iteration. Anthropic's own guidance is explicit here: start
with a workflow, add agency only when the task genuinely needs dynamic
routing or open-ended exploration. Term-candidate drafting from a grep
snippet doesn't; deciding whether a retrieved document chunk actually
answers a compliance question - where "check again with a different
query" is a real, sometimes-necessary move - does. The new slice targets
exactly that second shape of problem, and existing code stays exactly as
it is.

## Consequences

**Good:**

- Closes the single most-named gap across Cluster A's postings with code,
  not a framework import - the graph is small enough (3 node types) to
  explain and defend line-by-line, matching this repo's working agreement
- Checkpointing and the interrupt primitive give the audit-trail pillar
  (ADR-0021, planned) a structural hook to attach to, rather than bolting
  logging onto an ad-hoc loop after the fact
- LangSmith tracing (or a self-hosted equivalent) doubles as the
  observability story for the DevOps/observability pillar - one artifact,
  two pillars

**Bad:**

- A second orchestration concept in the repo (Dagster for the ETL-shaped
  pipeline, LangGraph for the agent loop) - has to be explained clearly or
  it reads as tool-collecting; the distinction (fixed pipeline vs. model-
  directed loop) is the whole point of this ADR, so the explanation
  already exists
- LangGraph's own learning curve (checkpointer setup, state schema design)
  is new surface area with no prior art in this codebase to lean on
- Token/latency cost per agentic run is higher than the single-call
  workflow it sits beside - needs the same cost/latency tracking this
  project already does for Boss Round LLM calls, extended to this path

## Alternatives considered

**CrewAI for faster initial velocity.** Rejected: the observability and
per-step error handling gap directly undercuts the compliance/audit
framing that is the whole reason this pillar exists. Cheaper to build,
more expensive to defend in an interview about a regulated-domain
platform.

**Hand-rolled loop, no framework.** Rejected for this repo's purposes
specifically: the interview point of this pillar is demonstrating agent
*orchestration* competency, and a framework most production teams
converged on demonstrates "I know what the field actually uses," where a
bespoke loop demonstrates only "I can write a while loop with retries."

**Do nothing; call the existing tool-use loop sufficient.** Rejected per
the Context section - it doesn't match what any of the 12 postings mean
by "agentic," and skills-map's own gap analysis already flagged this.

## When I would change this

- If LangGraph's checkpointing or interrupt primitives turn out to fight
  Dagster's asset model when the two need to compose (e.g., an agentic
  step feeding back into a Dagster-tracked asset), revisit whether the new
  slice should run inside or alongside Dagster's scheduler - not a reason
  to drop LangGraph, a question of where the seam sits.
- If a later posting cluster shows CrewAI's role-based model matching a
  different, non-compliance workflow better (e.g., a multi-agent
  brainstorming task with no audit requirement), CrewAI can coexist as a
  second tool for a different job - this ADR scopes LangGraph to the
  compliance-review agent specifically, not to "all future agent work."
- If token/latency cost measured in production (once this ships) shows the
  critique-loop rarely triggers a second retrieval pass, that's a signal
  the workflow-vs-agent line was drawn in the wrong place for this task,
  and the node should collapse back into a fixed two-step workflow.
