# How to Play

You're shown a term — an abbreviation or short piece of jargon (`CAP`,
`UoW`, `RAG`). Type what it means and submit. You get graded and shown
feedback immediately, then move to the next term.

## Scoring

Each answer is scored 0–100 across four components:

| Component | Points | What it checks |
| --- | --- | --- |
| Concept | 40 | Do you know what it actually is? |
| Expansion | 30 | Do you know what the letters stand for? |
| Purpose | 20 | Do you know what it's for? |
| Example | 10 | Can you ground it in something concrete? |

Typing just the expansion ("Unit of Work") scores 30. Explaining the
concept, purpose, and giving an example scores up to 100 — that inversion
is deliberate: recognizing an acronym is worth less than understanding it.

**Phase 1** (current): grading is deterministic — exact match, known
alias, or fuzzy text similarity against the expansion. Only the
Expansion component can score; Concept/Purpose/Example are 0 until
Phase 2.

**Phase 2** (planned): an LLM judge grades the full explanation against
all four components.

## Verdicts

- **Correct** — matched exactly, via a known alias, or fuzzy match ≥0.62
  similarity.
- **Partial** — fuzzy match between 0.40 and 0.62; you were close.
- **Incorrect** — below 0.40, or no match.

## Matched via

Shown alongside your result — which check produced the verdict:

- **exact** — you typed the expansion exactly.
- **alias** — you typed a recognized alternate spelling.
- **fuzzy** — text-similarity match against the expansion.
- **llm_rubric** — graded by the LLM judge (Phase 2).

## Sessions

Every answer you submit is recorded against your session (stored in your
browser, survives a refresh). There's no login yet — a session is tied to
this browser only.

## What's not here yet

No timer, no lives, no streak bonus, no game modes (Sprint/Survival/Boss
Round) — those are on the [roadmap](../README.md#next-steps). Today it's
one term at a time, graded, repeat.
