import { useEffect, useState } from "react";
import {
  getRandomTermTermsRandomGet,
  submitAnswerGameRoundsRoundIdAnswersSubmitPost,
} from "./client";
import type { SubmitAnswerResponse, TermPromptResponse } from "./client";
import { submitAnswerStream } from "./submitAnswerStream";

const ROUND_ID_KEY = "term-rush-round-id";
const THEME_KEY = "term-rush-theme";
const ROUND_LENGTH = 10;

const THEMES = ["phosphor", "devtool", "synthwave"] as const;
type Theme = (typeof THEMES)[number];

function getOrCreateRoundId(): string {
  const existing = localStorage.getItem(ROUND_ID_KEY);
  if (existing) return existing;
  const created = crypto.randomUUID();
  localStorage.setItem(ROUND_ID_KEY, created);
  return created;
}

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
  onCycle,
}: {
  theme: Theme;
  onCycle: () => void;
}) {
  return (
    <button
      onClick={onCycle}
      aria-label={`Switch theme (currently ${theme})`}
      className="fixed top-4 right-4 text-xs text-text-muted hover:text-text border border-surface-border hover:border-phosphor px-2 py-1 transition"
    >
      {theme}
    </button>
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
  onPlayAgain,
}: {
  answers: SubmitAnswerResponse[];
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
        <p className="text-sm text-text-dim mb-1"># round complete</p>
        <p className="text-3xl font-bold tracking-tight">
          {totalScore}/{ROUND_LENGTH * 100}
        </p>
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
  const [roundId] = useState(getOrCreateRoundId);
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

  const roundComplete = answers.length >= ROUND_LENGTH;

  const loadTerm = async () => {
    setError(null);
    setResult(null);
    setAnswer("");
    setLiveFeedback(null);
    const { data } = await getRandomTermTermsRandomGet({
      query: { round_id: roundId },
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

  const startNewRound = () => {
    setAnswers([]);
    loadTerm();
  };

  useEffect(() => {
    loadTerm();
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const cycleTheme = () => {
    setTheme((prev) => THEMES[(THEMES.indexOf(prev) + 1) % THEMES.length]);
  };

  const finishGrading = (data: SubmitAnswerResponse) => {
    setResult(data);
    setAnswers((prev) => [...prev, data]);
    // liveFeedback is intentionally left as-is here: ResultPanel shows it
    // instead of result.feedback for an LLM-graded answer (see its props
    // comment) — cleared on the next loadTerm(), not on every grade.
  };

  const submitAnswer = async () => {
    if (!term || !answer.trim()) return;
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
      <ThemeToggle theme={theme} onCycle={cycleTheme} />
      <main className="w-full max-w-md space-y-6">
        <h1 className="text-2xl font-bold tracking-tight text-center">
          <span className="text-phosphor">~/</span>term-rush
          <span className="animate-pulse text-phosphor">_</span>
        </h1>

        <HowToPlay />

        {!roundComplete && (
          <p className="text-sm text-text-dim text-center">
            term {Math.min(answers.length + 1, ROUND_LENGTH)}/{ROUND_LENGTH}
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
                (error.retryAction === "load" ? loadTerm : submitAnswer)();
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
            onContinue={roundComplete ? () => setResult(null) : loadTerm}
          />
        )}

        {roundComplete && !result && (
          <RoundSummary answers={answers} onPlayAgain={startNewRound} />
        )}
      </main>
    </div>
  );
}
