# PRD Template

Copy this when scoping a new phase, before writing any code. Fill in the
blanks, delete the guidance comments. Lives upstream of
[roadmap.md](./roadmap.md): a phase gets a PRD while scope is still moving,
then collapses into a roadmap.md entry (+ an ADR for the real trade-off
reasoning) once it ships. Don't keep both long-term — the PRD is scaffolding,
not a permanent record.

---

# PRD: \<Phase name\>

- **Tag:** Product | Skills-practice | Both — <!-- which axis, see roadmap.md § Product vs. skills-practice. Pick one primary reason even if it's Both. -->
- **Status:** Draft | Building | Shipped

## Problem

<!-- The gap in the product, or the skill not yet demonstrated. For
Skills-practice, name the skill and why this product is a plausible vehicle
for it — not a fabricated user pain. -->

## Decision

<!-- The approach chosen, one paragraph. Not a menu of alternatives — the
alternatives-and-why belongs in the ADR this phase will produce. -->

## Non-goals

- <!-- What's explicitly out of scope this phase, so scope doesn't creep
mid-build. -->

## Requirements

- <!-- Must / Should / Could. Keep it short — this isn't a spec, it's a
scope fence. -->

## Verification

<!-- How you'll know it's done: which command, which manual check, which
E2E scenario. Not a growth metric — see game-rules.md/skills-map.md's own
"honest" conventions. -->

## Constraints & assumptions

- <!-- Deadlines (rare here), dependencies on an earlier phase, known
unknowns. -->

## Open questions

- <!-- Unresolved decisions to close before build starts. -->

---

## Best practices

- **Lead with the problem.** If you can't restate it in one sentence after
  writing this section, the phase isn't scoped yet.
- **Tag before anything else.** Product vs. Skills-practice changes what
  "done" even means — a Skills-practice phase is done when the skill is
  demonstrated and defended in an ADR, not when a user metric moves.
- **Non-goals over goals.** This repo's scope creep has historically come
  from overlapping, undated plan files, not from missing goals. Say what
  this phase is *not* doing.
- **Frozen at commitment.** Edit freely before code starts. Once building,
  a scope change gets a note in Open questions or a new PRD, not a silent
  rewrite.
- **PRD dies at shipment.** Don't let both a PRD and a roadmap.md entry
  describe the same shipped phase — the PRD's content moves into
  roadmap.md (and the ADR), then the PRD file can be deleted.
