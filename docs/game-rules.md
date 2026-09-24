# How to Play

You're shown a term — an abbreviation or short piece of jargon (`CAP`,
`UoW`, `RAG`). Type what it means and submit. You get graded and shown
feedback immediately, then move to the next term.

## Game modes

- **Classic** — untimed, one term at a time, no cap besides a generous
  safety ceiling. The default.
- **Sprint** — a countdown starts on round creation. The browser setting
  offers 10, 30, 60, 120, or 300 seconds; 60 seconds is the default. The
  round ends when the timer expires, regardless of how many terms you've
  answered. AI feedback is unavailable — the streaming latency works
  against a timed mode's point.
- **Survival** — 3 lives. Each **Incorrect** verdict costs one life;
  **Partial**/**Correct** are free. The round ends the moment lives hit
  zero. Untimed, scored the same as Classic.
- **Boss Round** — exactly one term, drawn from the hardest, most
  well-defined entries in the bank. One answer, then the round ends
  regardless of verdict. AI feedback is always on for this one answer —
  there's no toggle, because the whole point is a real, high-stakes
  grading pass.
- **Daily 20** — a shared set of 20 terms, the same for everyone playing
  that UTC calendar day (like a daily word puzzle). You can replay as many
  times as you like; there's no "already played" lock since there's no
  login. AI feedback is off, so everyone's score means the same thing.

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

Grading always starts deterministic — exact match, known alias, or fuzzy
text similarity against the expansion — and only the Expansion component
can score there; Concept/Purpose/Example stay 0 unless the LLM judge grades
the answer.

The active round HUD shows cumulative score and current streak. Score is the
sum of server-returned answer scores. A streak counts consecutive **Correct**
verdicts and resets on **Partial** or **Incorrect**. A streak does not change
the score.

## Getting AI feedback

Check **"Get AI feedback on ambiguous answers"** before submitting. It only
does something when your deterministic verdict comes back **Partial** —
the ambiguous case the fuzzy matcher itself is least sure about. A clear
match or a clear miss is trusted as-is; the LLM only adjudicates the
middle.

When it kicks in, feedback streams in live, sentence by sentence, while
the judge is still writing it. A moment after the text finishes, the
final score appears with the full four-part breakdown. If the LLM call
fails for any reason, you silently keep the deterministic score instead —
grading never blocks on it.

Answers are also checked for offensive content before anything else runs;
a flagged answer scores 0 and skips grading entirely, regardless of the
toggle.

## Verdicts

- **Correct** — matched exactly, via a known alias, or fuzzy match ≥0.62
  similarity, or the LLM judge scored ≥70/100.
- **Partial** — fuzzy match between 0.40 and 0.62 (or, after LLM
  escalation, a score between 40 and 69).
- **Incorrect** — below 0.40 with no LLM escalation, an LLM score below
  40, or a flagged offensive answer.

## Matched via

Shown alongside your result — which check produced the verdict:

- **exact** — you typed the expansion exactly.
- **alias** — you typed a recognized alternate spelling.
- **fuzzy** — text-similarity match against the expansion.
- **llm_rubric** — graded by the LLM judge, after a Partial verdict and
  opting in.
- **flagged** — the answer was rejected as offensive before grading.

## Sessions

Every answer you submit is recorded against your session (stored in your
browser, survives a refresh). There's no login yet — a session is tied to
this browser only.

## Term selection

Each new term avoids ones you've already answered this session — no
back-to-back repeats mid-round. Once every term in the bank has come up,
repeats resume (there's nothing else left to show).

A **difficulty** picker on the setup screen (next to collection and mode)
lets you set a minimum floor — Trivial through Expert — sent as `GET
/terms/random?difficulty=`. It's a floor, not an exact match: "Hard" means
Hard-or-above. Boss Round ignores it: it always demands a boss-eligible
term, regardless of what's picked.

## Browser settings

Theme, voice language, and Sprint duration are stored in the current browser's
local storage. They are preferences, not player account data. Voice language
offers English (US) and English (UK). Authoritative gameplay limits are served
by `GET /game-config` (also available via the `gameConfig` field of the
`sessionScreen` GraphQL query, which the client uses at page load).

## What's not here yet

No streak score bonus, no login (so no per-player Daily 20 lock or persisted
best-times), no falling-term arcade gameplay, and no spaced repetition —
those are on the [roadmap](../README.md#next-steps).
