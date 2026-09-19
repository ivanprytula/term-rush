import { useEffect, useState } from "react";
import {
  getRandomTermTermsRandomGet,
  submitAnswerSessionsSessionIdAnswersSubmitPost,
} from "./client";
import type { SubmitAnswerResponse, TermPromptResponse } from "./client";

const SESSION_ID_KEY = "term-rush-session-id";
const ROUND_LENGTH = 10;

function getOrCreateSessionId(): string {
  const existing = localStorage.getItem(SESSION_ID_KEY);
  if (existing) return existing;
  const created = crypto.randomUUID();
  localStorage.setItem(SESSION_ID_KEY, created);
  return created;
}

const VERDICT_STYLE: Record<string, { color: string; label: string }> = {
  correct: { color: "text-green-400", label: "Correct" },
  partial: { color: "text-yellow-400", label: "Partially correct" },
  incorrect: { color: "text-slate-300", label: "Not quite" },
};

// Color alone doesn't carry the verdict (WCAG 1.4.1) — each state gets its
// own label text too. Incorrect reads muted, not alarming: a wrong answer
// is normal mid-round, not a failure state worth a loud red flag.
function verdictDisplay(verdict: string): { color: string; label: string } {
  return VERDICT_STYLE[verdict] ?? VERDICT_STYLE.incorrect;
}

// Deterministic grading only scores Expansion today; Concept/Purpose/Example
// always read 0. Shown so a low score reads as "not graded yet", not "you
// got this wrong" — see docs/game-rules.md.
function RubricNote({ rubric }: { rubric: SubmitAnswerResponse["rubric"] }) {
  return (
    <p className="text-xs text-slate-500">
      Expansion {rubric.expansion}/30 scored · Concept, Purpose, and Example
      aren't graded yet
    </p>
  );
}

function ResultPanel({
  result,
  continueLabel,
  onContinue,
}: {
  result: SubmitAnswerResponse;
  continueLabel: string;
  onContinue: () => void;
}) {
  const verdict = verdictDisplay(result.verdict);
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 space-y-3">
      <p className={`text-xl font-bold ${verdict.color}`}>
        {verdict.label} · <span className="font-mono">{result.score}/100</span>
      </p>
      <RubricNote rubric={result.rubric} />
      <p className="text-slate-300 text-sm">{result.feedback}</p>
      <button
        onClick={onContinue}
        className="w-full rounded-lg bg-sky-600 hover:bg-sky-500 px-4 py-3 font-medium transition"
      >
        {continueLabel}
      </button>
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
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 space-y-4 text-center">
      <div>
        <p className="text-sm text-slate-400 mb-1">Round complete</p>
        <p className="text-3xl font-mono font-bold tracking-tight">
          {totalScore}/{ROUND_LENGTH * 100}
        </p>
      </div>
      <div className="flex justify-center gap-4 text-sm">
        <span className="text-green-400">{counts.correct} correct</span>
        <span className="text-yellow-400">{counts.partial} partial</span>
        <span className="text-red-400">{counts.incorrect} incorrect</span>
      </div>
      <button
        onClick={onPlayAgain}
        className="w-full rounded-lg bg-sky-600 hover:bg-sky-500 px-4 py-3 font-medium transition"
      >
        Play again
      </button>
    </div>
  );
}

// Condensed for in-app reading; full rules live in docs/game-rules.md.
function HowToPlay() {
  return (
    <details className="bg-slate-900 border border-slate-700 rounded-xl text-sm text-slate-300 open:pb-4">
      <summary className="cursor-pointer select-none px-4 py-3 font-medium text-slate-100">
        How to play
      </summary>
      <div className="px-4 space-y-3">
        <p>
          You're shown a term. Type what it means and submit — you're
          graded immediately, then move to the next term.
        </p>
        <div>
          <p className="font-medium text-slate-200 mb-1">Scoring (0–100)</p>
          <ul className="list-disc list-inside space-y-0.5">
            <li>Concept (40) — do you know what it is?</li>
            <li>Expansion (30) — do you know what it stands for?</li>
            <li>Purpose (20) — do you know what it's for?</li>
            <li>Example (10) — can you ground it concretely?</li>
          </ul>
        </div>
        <p>
          Only Expansion scores today — grading is deterministic (exact /
          alias / fuzzy match). An LLM judge that grades all four is
          planned.
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
  const [sessionId] = useState(getOrCreateSessionId);
  const [term, setTerm] = useState<TermPromptResponse | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<SubmitAnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<AppError | null>(null);
  const [answers, setAnswers] = useState<SubmitAnswerResponse[]>([]);

  const roundComplete = answers.length >= ROUND_LENGTH;

  const loadTerm = async () => {
    setError(null);
    setResult(null);
    setAnswer("");
    const { data } = await getRandomTermTermsRandomGet();
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

  const submitAnswer = async () => {
    if (!term || !answer.trim()) return;
    setLoading(true);
    setError(null);
    const { data } = await submitAnswerSessionsSessionIdAnswersSubmitPost({
      path: { session_id: sessionId },
      body: { term_id: term.id, answer },
    });
    setLoading(false);
    if (!data) {
      setError({ message: "Grading failed.", retryAction: "submit" });
      return;
    }
    setResult(data);
    setAnswers((prev) => [...prev, data]);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitAnswer();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6">
        <h1 className="text-2xl font-bold tracking-tight text-center">
          Term Rush
        </h1>

        <HowToPlay />

        {!roundComplete && (
          <p className="text-sm text-slate-500 text-center font-mono">
            Term {Math.min(answers.length + 1, ROUND_LENGTH)}/{ROUND_LENGTH}
          </p>
        )}

        {error && (
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 space-y-3 text-center">
            <p className="text-red-400 text-sm">{error.message}</p>
            <button
              onClick={error.retryAction === "load" ? loadTerm : submitAnswer}
              className="w-full rounded-lg bg-sky-600 hover:bg-sky-500 px-4 py-3 font-medium transition"
            >
              Retry
            </button>
          </div>
        )}

        {term && !result && !roundComplete && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-slate-900 border border-sky-800 rounded-xl p-6 text-center">
              <p className="text-sm text-slate-400 mb-1">Define this term:</p>
              <p className="text-3xl font-mono font-bold tracking-tight">
                {term.term}
              </p>
            </div>
            <input
              autoFocus
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Type your answer…"
              className="w-full rounded-lg bg-slate-900 border border-slate-700 px-4 py-3 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-sky-500"
            />
            <button
              type="submit"
              disabled={loading || !answer.trim()}
              className="w-full rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-3 font-medium transition"
            >
              {loading ? "Grading…" : "Submit"}
            </button>
          </form>
        )}

        {result && (
          <ResultPanel
            result={result}
            continueLabel={roundComplete ? "See results" : "Next term"}
            onContinue={roundComplete ? () => setResult(null) : loadTerm}
          />
        )}

        {roundComplete && !result && (
          <RoundSummary answers={answers} onPlayAgain={startNewRound} />
        )}
      </div>
    </div>
  );
}
