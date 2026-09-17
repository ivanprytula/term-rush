# ADR-0002: Grading strategy — deterministic chain now, LLM rubric later

- **Status:** Accepted
- **Date:** 2026-09-17
- **Referenced from:** `domain/evaluation/graders.py`, `domain/evaluation/outcome.py`

## Context

The prototype graded answers with one 6-line function: normalize both strings, check
equality, check substring, else count overlapping tokens. Pass at 0.62.

That is fine for `CPU = Central Processing Unit`. It is actively wrong for the terms
that matter. Consider `UoW`:

| Answer | Prototype verdict | What the player actually knows |
|---|---|---|
| "Unit of Work" | ✅ pass | the expansion, nothing more |
| "Unit" | ✅ pass (0.88, substring!) | almost nothing |
| "groups database changes into one transaction" | ❌ fail (0.0) | **the actual concept** |

The third row is the problem. The prototype rewards memorization and punishes
understanding — the exact inverse of the product's purpose. A player who can explain
what a Unit of Work is *for* scores zero, while a player who typed one word passes.

## Decision

Two decisions, staged.

### 1. A grader chain with an abstain protocol (Phase 1)

`Grader` is a Protocol with `grade(answer, term) -> GradeOutcome | None`, where
`None` means "I have no opinion, ask the next grader" — distinct from returning a
zero score, which would end the chain. Ordered cheapest-and-most-certain first:

```
ExactGrader → AliasGrader → FuzzyGrader → [LLMRubricGrader, Phase 2]
```

The common case (exact expansion typed) resolves in one string comparison and never
touches the expensive path. The final grader in any chain must never abstain;
`AnswerEvaluator` raises `RuntimeError` if the chain exhausts, treating it as the
programming error it would be.

**This is the Open/Closed seam.** Adding the LLM judge in Phase 2 appends one entry
to a tuple. Zero changes to `AnswerEvaluator`, to the use cases, or to the API.

### 2. A four-part rubric, weighted against memorization (Phase 2)

| Slice | Weight | Question it answers |
|---|---|---|
| Expansion | 30 | Do you know what the letters stand for? |
| Concept | 40 | Do you know what it *is*? |
| Purpose | 20 | Do you know what it is *for*? |
| Example | 10 | Can you ground it in something concrete? |

Deliberately, **expansion is worth less than concept**. "Unit of Work" scores 30.
"Unit of Work, a pattern that groups database changes into one transaction" scores
90. That inversion is the entire product thesis, and it is pinned by a test
(`test_understanding_outscores_memorization`).

Deterministic graders can only ever award the expansion slice — they are
structurally incapable of judging whether a player understood the concept, so they
award `RubricBreakdown.expansion_only()` and leave the other 70 points unearned.

## Known weakness, accepted deliberately

The substring rule inherited from the prototype is generous to the point of being
wrong: `similarity("Unit", "Unit of Work") == 0.88`, so a single word passes. This
is verified and pinned in `test_single_word_substring_is_accepted`.

I am **keeping** it for Phase 1 rather than tightening the threshold, because:

1. Tightening trades false-accepts for false-rejects, and a false-reject in an
   arcade game feels far worse than a lucky pass — it reads as the game being broken.
2. The real fix is not a better string heuristic. It is the rubric judge, which asks
   "did they explain the concept?" instead of "do the characters overlap?". Investing
   in threshold-tuning now is polishing something Phase 2 replaces.
3. Deterministic grading caps at 30/100 anyway. A lucky substring pass earns the
   player a weak score and an immediate SRS reschedule — the learning engine
   self-corrects what the grader got wrong.

The port was verified against the original JavaScript across 11 cases; Python and JS
agree exactly. The behaviour is inherited, not accidentally reinvented.

## Alternatives considered

**Local sentence-transformer embeddings in Phase 1.** Semantic similarity for free,
~100ms, no API key. Rejected: adds a ~500MB model dependency to the Phase 1 container
for a capability Phase 2 supersedes, and embedding cosine similarity still cannot
produce a *breakdown* — it gives one number, not "you missed the purpose".

**Synchronous LLM grading from Phase 1.** Simpler mental model, one code path.
Rejected: every answer costs money and 1–2s of latency in a game where terms are
falling; Phase 1 demos would require an API key to work at all; and there would be no
fallback when the LLM is down.

**Just tighten the threshold to 0.75.** Rejected, see "Known weakness" above.

## When I would change this

- If the LLM judge proves reliable and cheap enough to run inline (sub-300ms, cached
  aggressively), collapse the chain and drop the fuzzy grader to a pure fallback.
- If `matched_via` analytics show `FUZZY` accepting answers the LLM later grades
  below 40, the substring rule has become a measurable problem rather than a
  theoretical one — tighten it then, with data.
- If the game ever adds non-English terms, `normalize()`'s `[^a-z0-9]` stripping
  destroys them. That is a rewrite, not a tweak.
