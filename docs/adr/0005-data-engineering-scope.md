# ADR-0005: Data engineering scope — batch ELT, quality, lineage, warehouse

- **Status:** Accepted
- **Date:** 2026-09-17
- **Related:** ADR-0004 (term bank is mined from the repo)

## Context

Two distinct data workloads exist in this project, and conflating them would be a
design error:

1. **Content pipeline** — mine the repo, enrich, validate, publish the term bank
   (ADR-0004). Batch. Runs on commit or on demand. Correctness matters far more than
   latency.
2. **Learning analytics** — turn a stream of `AnswerGraded` events into the facts that
   drive the learning engine: which terms are weak, which prerequisites are actually
   blocking, how difficulty is calibrated against real player performance. Batch is
   sufficient; the learning engine schedules reviews in *days*, not milliseconds.

Neither needs streaming. Saying so out loud matters, because reaching for Flink when
a nightly batch job would do is the exact instinct this project is documenting against.

## Decision

**Batch ELT with first-class data quality, lineage and a dimensional warehouse.
Streaming is deliberately deferred, with a stated trigger.**

### Stack, and why each

| Concern | Choice | Reasoning |
|---|---|---|
| Orchestration | **Dagster** | Asset-oriented rather than task-oriented: you declare *the term bank* as an asset with dependencies, and lineage comes free. Better fit than Airflow for a data-product-shaped graph, and materially nicer locally. Airflow noted as the incumbent alternative. |
| Transformation | **dbt Core** | SQL-first, version-controlled, testable. `dbt test` is the quality gate. The industry default for good reason. |
| Warehouse (local) | **DuckDB** | Zero-ops, fast, runs in CI. The whole warehouse is a file. |
| Warehouse (cloud) | **BigQuery** | GCP-native, generous free tier, same dbt models with a different profile — which is the portability demonstration. |
| Quality | **dbt tests + Pydantic contracts** | Two layers: schema/type at ingest (Pydantic), relational/distributional in the warehouse (dbt). |
| Lineage | **Dagster asset graph + dbt DAG** | Column-level where dbt provides it; asset-level across the whole pipeline. |

### Dimensional model

A star schema, because the queries are analytical and the grain is obvious:

```
              dim_term ──┐
                         │
              dim_user ──┼──▶ fct_answer        (grain: one graded answer)
                         │
              dim_date ──┤
                         │
    dim_game_mode ───────┘

                         └──▶ fct_review_schedule (grain: one card state transition)
```

Marts built on top:

- `mart_term_difficulty` — observed difficulty per term from real answer data, which
  feeds back into the learning engine. **The loop closes**: the game produces the data
  that recalibrates the game.
- `mart_user_mastery` — per-user, per-category mastery for Weakness Mode.
- `mart_prerequisite_efficacy` — do the prerequisite edges predict success? This
  validates the term bank's own graph against reality, and can flag bad LLM-authored
  prerequisites.
- `mart_content_health` — coverage, staleness, review-queue depth, enrichment failures.

`mart_term_difficulty` is the interesting one: it makes the analytics **load-bearing**
rather than a dashboard nobody opens. If the pipeline breaks, difficulty calibration
goes stale and the game measurably degrades.

### Slowly changing dimensions

`dim_term` is **SCD Type 2**. Terms get re-enriched; definitions change. A player's
answer from March must be interpretable against the definition that existed in March,
not today's. This is a real requirement, not an excuse to demonstrate SCD2.

### Idempotency and backfill

Every asset is idempotent and partitioned by date. Re-running a partition produces the
same result. Backfills are a first-class operation, not a disaster recovery story.

## Deliberately deferred: streaming

**Not building** CDC (Debezium), stream processing (Flink/Kafka Streams), or a
lakehouse table format (Iceberg/Delta) — for now.

Why not:

- The learning engine operates on daily review intervals. Sub-second freshness buys
  nothing a user can perceive.
- The live leaderboard already updates in real time via **Redis ZSET** — the right tool
  for that specific job, and it needs no stream processor.
- CDC + Flink + Iceberg is three more systems to run, monitor and explain, for latency
  nobody requested.

**Trigger to revisit:** if a feature genuinely needs sub-minute analytical freshness —
live cohort comparison during a session, or real-time difficulty adjustment *within*
a run — then Kafka is already in the architecture from Phase 3, and the incremental
step is a consumer writing to the warehouse, not a re-platform. The path is open; the
cost is not paid until it is needed.

Documenting this refusal is the point. *Knowing when not to add infrastructure is the
skill being demonstrated*, and it is the same argument as ADR-0012 (pgvector over a
dedicated vector DB).

## Consequences

**Good:**
- Covers the large majority of what data-engineering interviews probe: modeling,
  orchestration, quality, lineage, idempotency, SCD, backfill.
- Runs free locally (DuckDB) and free-tier in cloud (BigQuery).
- Analytics is load-bearing, so pipeline breakage is visible rather than silent.
- Closed loop: game → events → warehouse → difficulty calibration → game.

**Bad:**
- Dagster + dbt is a real learning curve on top of an already large project.
- A star schema over a few thousand rows is over-modeled for the data volume. Accepted
  deliberately — the schema must be *right* to be worth demonstrating, and synthetic
  event generation will provide realistic volume for the performance work.
- Two warehouse targets (DuckDB, BigQuery) means two dbt profiles and occasional
  dialect friction. Mitigated by keeping models ANSI-ish and testing both in CI.

## When I would change this

- Volume beyond ~10M facts → partitioning and clustering strategy needs real thought;
  DuckDB local stops being representative.
- If a sub-minute-freshness feature ships → add the streaming tier per the trigger above.
- If dbt model count passes ~40 → introduce a proper staging/intermediate/marts
  convention with enforced naming, rather than letting it sprawl.
