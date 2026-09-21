import { useEffect, useState } from "react";
import {
  createRoundGameRoundsPost,
  getRandomTermTermsRandomGet,
  getTermCategoriesTermsCategoriesGet,
  submitAnswerGameRoundsRoundIdAnswersSubmitPost,
} from "./client";
import type { SubmitAnswerResponse, TermPromptResponse } from "./client";
import { submitAnswerStream } from "./submitAnswerStream";
import { useSprintCountdown } from "./useSprintCountdown";

const THEME_KEY = "term-rush-theme";
const ROUND_LENGTH = 10;

const THEMES = [
  "phosphor",
  "devtool",
  "synthwave",
  "solarized",
  "high-contrast",
  "nord",
] as const;
type Theme = (typeof THEMES)[number];

// index.html's inline pre-paint script already set data-theme on <html>
// from localStorage (or left it unset, meaning "phosphor" via :root's
// default) — read that same source so React's state agrees with what's
// already on screen instead of flashing a second theme on mount.
function getInitialTheme(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  return (THEMES as readonly string[]).includes(attr ?? "")
    ? (attr as Theme)
    : "phosphor";
}

function ThemeToggle({
  theme,
  onChange,
}: {
  theme: Theme;
  onChange: (theme: Theme) => void;
}) {
  return (
    <select
      value={theme}
      onChange={(e) => onChange(e.target.value as Theme)}
      aria-label="Switch theme"
      className="fixed top-4 right-4 text-xs text-text-muted hover:text-text border border-surface-border hover:border-phosphor px-2 py-1 transition bg-surface"
    >
      {THEMES.map((t) => (
        <option key={t} value={t}>
          {t}
        </option>
      ))}
    </select>
  );
}

// null means "All terms" (no filter) — the <select>'s own empty-string
// option, not a real category slug, so it can't collide with one.
const ALL_TERMS = "";

function CategoryPicker({
  categories,
  selected,
  onChange,
}: {
  categories: string[];
  selected: string | null;
  onChange: (category: string | null) => void;
}) {
  // Nothing to pick from yet (still loading, or the bank has no tagged
  // categories) — rather than show a dropdown with only "All terms" in it.
  if (categories.length === 0) return null;
  return (
    <label className="flex items-center justify-center gap-2 text-sm text-text-dim">
      collection
      <select
        value={selected ?? ALL_TERMS}
        onChange={(e) =>
          onChange(e.target.value === ALL_TERMS ? null : e.target.value)
        }
        className="bg-surface border border-surface-border text-text px-2 py-1 focus:outline-none focus:border-phosphor"
      >
        <option value={ALL_TERMS}>All terms</option>
        {categories.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </label>
  );
}

const VERDICT_STYLE: Record<string, { color: string; label: string }> = {
  correct: { color: "text-phosphor", label: "CORRECT" },
  partial: { color: "text-amber", label: "PARTIAL" },
  incorrect: { color: "text-text-muted", label: "NOT QUITE" },
};

// Color alone doesn't carry the verdict (WCAG 1.4.1) — bracket-delimited
// text label too, the way a test runner or linter reports status. Incorrect
// reads muted, not alarming: a wrong answer is normal mid-round, not a
// failure state worth a loud flag.
function verdictDisplay(verdict: string): { color: string; label: string } {
  return VERDICT_STYLE[verdict] ?? VERDICT_STYLE.incorrect;
}

// Deterministic grading only scores Expansion; Concept/Purpose/Example
// always read 0 there — shown so a low score reads as "not graded yet", not
// "you got this wrong" (see docs/game-rules.md). Once the LLM judge grades
// (matched_via "llm_rubric"), all four are real scores, so the caveat would
// be actively wrong — skip it.
function RubricNote({
  rubric,
  matchedVia,
}: {
  rubric: SubmitAnswerResponse["rubric"];
  matchedVia: string;
}) {
  if (matchedVia === "llm_rubric") return null;
  return (
    <p className="text-xs text-text-muted">
      expansion={rubric.expansion}/30 · concept, purpose, example not graded
      yet
    </p>
  );
}

function ResultPanel({
  result,
  requestedLlmGrading,
  streamedFeedback,
  continueLabel,
  onContinue,
}: {
  result: SubmitAnswerResponse;
  requestedLlmGrading: boolean;
  // The rationale text as it streamed in, kept on screen instead of
  // result.feedback once grading completes. They come from two separate
  // LLM calls (tool_use can't stream), so swapping one for the other at
  // the end reads as a jarring, near-duplicate replace — see llm_grader.py.
  streamedFeedback: string | null;
  continueLabel: string;
  onContinue: () => void;
}) {
  const verdict = verdictDisplay(result.verdict);
  const llmGraded = result.matched_via === "llm_rubric";
  return (
    <div className="bg-surface border border-surface-border p-6 space-y-3">
      <p className={`text-xl font-bold ${verdict.color}`}>
        [ {verdict.label} ] <span>{result.score}/100</span>
      </p>
      <RubricNote rubric={result.rubric} matchedVia={result.matched_via} />
      {/* Explains why AI feedback was requested but nothing streamed — the
          escalation only fires on a PARTIAL deterministic verdict, so a
          clear match or clear miss silently skips it otherwise. */}
      {requestedLlmGrading && !llmGraded && (
        <p className="text-xs text-text-muted">
          # AI feedback only kicks in on ambiguous answers — this one was
          clear-cut.
        </p>
      )}
      <p className="text-text-dim text-sm">
        {llmGraded && streamedFeedback ? streamedFeedback : result.feedback}
      </p>
      {/* <form> so Enter activates this too, not just a mouse click —
          matches native behavior, no keyboard listener needed. */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onContinue();
        }}
      >
        <button
          type="submit"
          autoFocus
          className="w-full bg-phosphor text-ground hover:bg-phosphor-dim px-4 py-3 font-bold transition"
        >
          {continueLabel}
        </button>
      </form>
    </div>
  );
}

function RoundSummary({
  answers,
  heading = "round complete",
  onPlayAgain,
}: {
  answers: SubmitAnswerResponse[];
  // "time's up" reuses this panel for a Sprint round's expiry screen —
  // same content (score + verdict breakdown), different trigger.
  heading?: string;
  onPlayAgain: () => void;
}) {
  const totalScore = answers.reduce((sum, a) => sum + a.score, 0);
  const counts = {
    correct: answers.filter((a) => a.verdict === "correct").length,
    partial: answers.filter((a) => a.verdict === "partial").length,
    incorrect: answers.filter((a) => a.verdict === "incorrect").length,
  };

  return (
    <div className="bg-surface border border-surface-border p-6 space-y-4 text-center">
      <div>
        <p className="text-sm text-text-dim mb-1"># {heading}</p>
        <p className="text-3xl font-bold tracking-tight">{totalScore}</p>
      </div>
      <div className="flex justify-center gap-4 text-sm">
        <span className="text-phosphor">{counts.correct} correct</span>
        <span className="text-amber">{counts.partial} partial</span>
        <span className="text-text-muted">{counts.incorrect} incorrect</span>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onPlayAgain();
        }}
      >
        <button
          type="submit"
          autoFocus
          className="w-full bg-phosphor text-ground hover:bg-phosphor-dim px-4 py-3 font-bold transition"
        >
          play again
        </button>
      </form>
    </div>
  );
}

// Condensed for in-app reading; full rules live in docs/game-rules.md.
function HowToPlay() {
  return (
    <details className="bg-surface border border-surface-border text-sm text-text-dim open:pb-4">
      <summary className="cursor-pointer select-none px-4 py-3 font-bold text-text">
        $ man term-rush
      </summary>
      <div className="px-4 space-y-3">
        <p>
          You're shown a term. Type what it means and submit — you're
          graded immediately, then move to the next term.
        </p>
        <div>
          <p className="font-bold text-text mb-1"># scoring (0-100)</p>
          <ul className="list-disc list-inside space-y-0.5">
            <li>concept (40) — do you know what it is?</li>
            <li>expansion (30) — do you know what it stands for?</li>
            <li>purpose (20) — do you know what it's for?</li>
            <li>example (10) — can you ground it concretely?</li>
          </ul>
        </div>
        <p>
          Only expansion scores by default — grading is deterministic
          (exact / alias / fuzzy match). Check "get AI feedback" to escalate
          ambiguous answers to an LLM judge that grades all four.
        </p>
      </div>
    </details>
  );
}

// Distinguishes "load failed" (no term to show, retry = fetch a new one)
// from "submit failed" (term/answer still on screen, retry = resubmit) so
// each error recovers correctly instead of both falling back to a reload.
type AppError = { message: string; retryAction: "load" | "submit" };

export default function App() {
  // Null until POST /game-rounds returns — the server mints the id, so
  // there's nothing to read synchronously the way a client-generated
  // UUID allowed before.
  const [roundId, setRoundId] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const [term, setTerm] = useState<TermPromptResponse | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<SubmitAnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<AppError | null>(null);
  const [answers, setAnswers] = useState<SubmitAnswerResponse[]>([]);
  // Opt-in: escalates a PARTIAL verdict to the LLM rubric judge, streamed
  // live. No effect on CORRECT/INCORRECT verdicts or if the server has no
  // LLM grader configured — see POST .../submit/stream docs.
  const [useLlmGrading, setUseLlmGrading] = useState(false);
  // Non-null while an LLM judge's feedback is streaming in; distinct from
  // `result` (the final graded outcome) so the UI can show growing text
  // before the rubric score exists.
  const [liveFeedback, setLiveFeedback] = useState<string | null>(null);
  // useLlmGrading's value at the moment `result` was requested — not the
  // live checkbox state, which the player could change before the result
  // renders. Answers "did we ask for AI feedback on this result?".
  const [requestedLlmGrading, setRequestedLlmGrading] = useState(false);
  // Checked before starting a round; changing it has no effect on a round
  // already in progress — mode is fixed server-side at creation.
  const [sprintMode, setSprintMode] = useState(false);
  // The round's own mode, as returned by the server — distinct from
  // sprintMode (the toggle for the *next* round to start).
  const [roundMode, setRoundMode] = useState<"classic" | "sprint">("classic");
  // Every collection the player can choose to play from — fetched once on
  // mount, not tied to any round.
  const [categories, setCategories] = useState<string[]>([]);
  // Picker's live value; null means "All terms". Unlike sprintMode/roundMode,
  // category isn't a round property server-side — it's a query param on
  // every GET /terms/random call, so roundCategory (below) is what actually
  // gets reused across a round's term fetches.
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  // Locked in at round start, same pattern as roundMode — changing the
  // picker mid-round has no effect until the next "start round"/"play again".
  const [roundCategory, setRoundCategory] = useState<string | null>(null);
  // Server's remaining_seconds as of the last round response; re-syncs the
  // rAF countdown below whenever a fresh round starts.
  const [serverRemaining, setServerRemaining] = useState<number | null>(null);
  const remainingSeconds = useSprintCountdown(serverRemaining);
  const sprintExpired = roundMode === "sprint" && remainingSeconds === 0;

  const roundComplete =
    roundMode === "classic" ? answers.length >= ROUND_LENGTH : sprintExpired;
  const started = roundId !== null;

  // category defaults to roundCategory (the round's locked-in choice) so
  // every call site except startRound (which hasn't locked it in yet this
  // tick) can omit the argument.
  const loadTerm = async (activeRoundId: string, category = roundCategory) => {
    setError(null);
    setResult(null);
    setAnswer("");
    setLiveFeedback(null);
    const { data } = await getRandomTermTermsRandomGet({
      query: { round_id: activeRoundId, category: category ?? undefined },
    });
    // The generated client can return a falsy `error` (e.g. "") on some
    // failure shapes, so check for a real response body instead of
    // trusting `error`'s truthiness.
    if (!data) {
      setError({ message: "Could not load a term.", retryAction: "load" });
      return;
    }
    setTerm(data);
  };

  // Starts a round server-side and loads its first term. Used both on
  // mount and on "play again" — each is a genuinely new round, not a
  // continuation, so both mint a fresh id rather than reusing one. Mode is
  // fixed by the sprintMode toggle at the moment the round starts; category
  // likewise locks in selectedCategory as roundCategory.
  const startRound = async () => {
    setError(null);
    setRoundCategory(selectedCategory);
    const { data } = await createRoundGameRoundsPost({
      body: { mode: sprintMode ? "sprint" : "classic" },
    });
    if (!data) {
      setError({ message: "Could not start a round.", retryAction: "load" });
      return;
    }
    setRoundId(data.id);
    setRoundMode(data.mode === "sprint" ? "sprint" : "classic");
    setServerRemaining(data.remaining_seconds ?? null);
    // Explicit selectedCategory, not loadTerm's roundCategory default:
    // setRoundCategory above hasn't committed yet in this same tick.
    await loadTerm(data.id, selectedCategory);
  };

  const startNewRound = () => {
    setAnswers([]);
    startRound();
  };

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  // Once per mount, not per round — the collection list doesn't change
  // mid-session. A failed fetch just means no picker renders (CategoryPicker
  // returns null on an empty list) rather than an error state; "All terms"
  // still works with zero categories loaded.
  useEffect(() => {
    getTermCategoriesTermsCategoriesGet()
      .then(({ data }) => {
        if (data) setCategories(data.categories);
      })
      // A network failure here just means no picker renders (see
      // CategoryPicker's empty-list guard) — "All terms" still works with
      // zero categories loaded, so this never becomes a blocking error.
      .catch(() => {});
  }, []);

  const finishGrading = (data: SubmitAnswerResponse) => {
    setResult(data);
    setAnswers((prev) => [...prev, data]);
    // liveFeedback is intentionally left as-is here: ResultPanel shows it
    // instead of result.feedback for an LLM-graded answer (see its props
    // comment) — cleared on the next loadTerm(), not on every grade.
  };

  const submitAnswer = async () => {
    // roundId is set by the time a term is on screen — startRound() always
    // loads a term after minting the round, never in either order.
    // sprintExpired: don't fire a submit the server would 422 anyway — the
    // countdown reaching 0 already flips to the time's-up screen below.
    if (!term || !answer.trim() || !roundId || sprintExpired) return;
    setLoading(true);
    setError(null);
    setRequestedLlmGrading(useLlmGrading);

    if (useLlmGrading) {
      setLiveFeedback("");
      await submitAnswerStream(
        roundId,
        { term_id: term.id, answer, use_llm_grading: true },
        {
          onRationaleDelta: (text) =>
            setLiveFeedback((prev) => (prev ?? "") + text),
          onGraded: (data) => {
            setLoading(false);
            finishGrading(data);
          },
          onError: (message) => {
            setLoading(false);
            setLiveFeedback(null);
            setError({ message, retryAction: "submit" });
          },
        },
      );
      return;
    }

    const { data } = await submitAnswerGameRoundsRoundIdAnswersSubmitPost({
      path: { round_id: roundId },
      body: { term_id: term.id, answer },
    });
    setLoading(false);
    if (!data) {
      setError({ message: "Grading failed.", retryAction: "submit" });
      return;
    }
    finishGrading(data);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitAnswer();
  };

  return (
    <div className="min-h-screen bg-ground text-text flex items-center justify-center p-4">
      <ThemeToggle theme={theme} onChange={setTheme} />
      <main className="w-full max-w-md space-y-6">
        <h1 className="text-2xl font-bold tracking-tight text-center">
          <span className="text-phosphor">~/</span>term-rush
          <span className="animate-pulse text-phosphor">_</span>
        </h1>

        <HowToPlay />

        {/* Mode is fixed server-side at round creation — the toggle only
            affects the round about to start, so it's shown before start
            and again once a round ends (via RoundSummary's "play again"),
            never mid-round. */}
        {!started && (
          <div className="bg-surface border border-surface-border p-6 space-y-4 text-center">
            <label className="flex items-center justify-center gap-2 text-sm text-text-dim">
              <input
                type="checkbox"
                checked={sprintMode}
                onChange={(e) => setSprintMode(e.target.checked)}
                className="accent-phosphor bg-surface border-surface-border"
              />
              sprint mode (60s countdown)
            </label>
            <CategoryPicker
              categories={categories}
              selected={selectedCategory}
              onChange={setSelectedCategory}
            />
            <button
              type="button"
              autoFocus
              onClick={startRound}
              className="w-full bg-phosphor text-ground hover:bg-phosphor-dim px-4 py-3 font-bold transition"
            >
              start round
            </button>
          </div>
        )}

        {started && !roundComplete && roundMode === "classic" && (
          <p className="text-sm text-text-dim text-center">
            term {Math.min(answers.length + 1, ROUND_LENGTH)}/{ROUND_LENGTH}
          </p>
        )}
        {started && !roundComplete && roundMode === "sprint" && (
          // aria-live: the number changes every frame — announcing every
          // tick would spam a screen reader, so this is visual-only; the
          // time's-up screen (an ordinary heading) is what gets announced.
          <p
            className="text-sm text-text-dim text-center tabular-nums"
            aria-hidden="true"
          >
            {"⏱ "}
            {Math.ceil(remainingSeconds ?? 0)}s
          </p>
        )}

        {error && (
          // role="alert": screen readers announce this the moment it
          // appears, without the user needing to navigate to find it —
          // sighted users already get that signal for free from the red text.
          <div
            role="alert"
            className="bg-surface border border-surface-border p-6 space-y-3 text-center"
          >
            <p className="text-amber text-sm">! {error.message}</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (error.retryAction === "submit") {
                  submitAnswer();
                } else if (roundId) {
                  loadTerm(roundId);
                } else {
                  startRound();
                }
              }}
            >
              <button
                type="submit"
                autoFocus
                className="w-full bg-phosphor text-ground hover:bg-phosphor-dim px-4 py-3 font-bold transition"
              >
                retry
              </button>
            </form>
          </div>
        )}

        {term && !result && !roundComplete && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-surface border border-phosphor-dim p-6 text-center">
              <p className="text-sm text-text-dim mb-1"># define this term</p>
              <p className="text-3xl font-bold tracking-tight">
                {term.term}
              </p>
            </div>
            <div className="flex items-center gap-2 bg-surface border border-surface-border px-4 py-3 focus-within:border-phosphor">
              <span className="text-phosphor select-none">&gt;</span>
              <input
                autoFocus
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="type your answer…"
                className="w-full bg-transparent text-text placeholder:text-text-muted focus:outline-none"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-text-dim">
              <input
                type="checkbox"
                checked={useLlmGrading}
                onChange={(e) => setUseLlmGrading(e.target.checked)}
                className="accent-phosphor bg-surface border-surface-border"
              />
              get AI feedback on ambiguous answers
            </label>
            {liveFeedback !== null && (
              <p className="text-sm text-text-dim italic min-h-5">
                {liveFeedback || "thinking…"}
              </p>
            )}
            <button
              type="submit"
              disabled={loading || !answer.trim()}
              className="w-full bg-phosphor text-ground hover:bg-phosphor-dim disabled:opacity-40 disabled:cursor-not-allowed px-4 py-3 font-bold transition"
            >
              {loading ? "grading…" : "submit"}
            </button>
          </form>
        )}

        {result && (
          <ResultPanel
            result={result}
            requestedLlmGrading={requestedLlmGrading}
            streamedFeedback={liveFeedback}
            continueLabel={roundComplete ? "see results" : "next term"}
            onContinue={
              roundComplete
                ? () => setResult(null)
                : () => roundId && loadTerm(roundId)
            }
          />
        )}

        {roundComplete && !result && (
          <RoundSummary
            answers={answers}
            heading={sprintExpired ? "time's up" : "round complete"}
            onPlayAgain={startNewRound}
          />
        )}
      </main>
    </div>
  );
}
