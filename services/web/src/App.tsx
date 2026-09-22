import { useEffect, useRef, useState } from "react";
import { Mic, MicOff } from "lucide-react";
import {
  createRoundGameRoundsPost,
  getRandomTermTermsRandomGet,
  getTermCategoriesTermsCategoriesGet,
  submitAnswerGameRoundsRoundIdAnswersSubmitPost,
} from "./client";
import type {
  RoundMode,
  SubmitAnswerResponse,
  TermPromptResponse,
} from "./client";
import { submitAnswerStream } from "./submitAnswerStream";
import { useSprintCountdown } from "./useSprintCountdown";
import { useSpeechRecognition } from "./useSpeechRecognition";

const THEME_KEY = "term-rush-theme";
const ROUND_LENGTH = 10;
const SURVIVAL_LIVES = 3; // mirrors constants.SURVIVAL_LIVES server-side

const MODES: readonly RoundMode[] = [
  "classic",
  "sprint",
  "survival",
  "boss",
  "daily_20",
];

const MODE_LABEL: Record<RoundMode, string> = {
  classic: "classic",
  sprint: "sprint — 60s countdown",
  survival: "survival — 3 lives",
  boss: "boss — one hard term, AI-graded",
  daily_20: "daily 20 — today's shared set",
};

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

function ModePicker({
  selected,
  onChange,
}: {
  selected: RoundMode;
  onChange: (mode: RoundMode) => void;
}) {
  return (
    <label className="flex items-center justify-center gap-2 text-sm text-text-dim">
      mode
      <select
        value={selected}
        onChange={(e) => onChange(e.target.value as RoundMode)}
        className="bg-surface border border-surface-border text-text px-2 py-1 focus:outline-none focus:border-phosphor"
      >
        {MODES.map((m) => (
          <option key={m} value={m}>
            {MODE_LABEL[m]}
          </option>
        ))}
      </select>
    </label>
  );
}

const VERDICT_STYLE: Record<string, { color: string; label: string }> = {
  correct: { color: "text-verdict-correct", label: "CORRECT" },
  partial: { color: "text-verdict-partial", label: "PARTIAL" },
  incorrect: { color: "text-verdict-incorrect", label: "NOT QUITE" },
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
  isBossRound,
  streamedFeedback,
  continueLabel,
  onContinue,
}: {
  result: SubmitAnswerResponse;
  requestedLlmGrading: boolean;
  // Boss mode's escalation is a mode policy, not the player's opt-in — the
  // "you asked, but it was clear-cut" caveat below doesn't apply to it and
  // needs its own message.
  isBossRound: boolean;
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
      {requestedLlmGrading && !llmGraded && isBossRound && (
        <p className="text-xs text-text-muted">
          # Boss rounds always grade with AI — the deterministic match here
          was already clear-cut, so escalation had nothing to add.
        </p>
      )}
      {/* Explains why AI feedback was requested but nothing streamed — the
          escalation only fires on a PARTIAL deterministic verdict, so a
          clear match or clear miss silently skips it otherwise. */}
      {requestedLlmGrading && !llmGraded && !isBossRound && (
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
  selectedMode,
  onModeChange,
  onPlayAgain,
}: {
  answers: SubmitAnswerResponse[];
  // Every mode's terminal state reuses this same panel — same content
  // (score + verdict breakdown), just a different heading per mode (see
  // ROUND_END_HEADING) for why the round ended.
  heading?: string;
  selectedMode: RoundMode;
  onModeChange: (mode: RoundMode) => void;
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
        <span className="text-verdict-correct">{counts.correct} correct</span>
        <span className="text-verdict-partial">{counts.partial} partial</span>
        <span className="text-verdict-incorrect">{counts.incorrect} incorrect</span>
      </div>
      <ModePicker selected={selectedMode} onChange={onModeChange} />
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
    <details className="fixed top-14 right-4 z-10 w-fit max-w-[calc(100vw-2rem)] bg-surface border border-surface-border text-sm text-text-dim open:pb-4">
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
  // Picker's live value for the *next* round to start; changing it has no
  // effect on a round already in progress — mode is fixed server-side at
  // creation.
  const [selectedMode, setSelectedMode] = useState<RoundMode>("classic");
  // The round's own mode, as returned by the server — distinct from
  // selectedMode (the picker for the *next* round to start).
  const [roundMode, setRoundMode] = useState<RoundMode>("classic");
  // Survival only, derived client-side from answers (SURVIVAL_LIVES minus
  // incorrect verdicts so far) — the server stays authoritative regardless
  // (still 422s past zero lives), same trust split Sprint's countdown uses.
  const livesRemaining =
    roundMode === "survival"
      ? Math.max(
          0,
          SURVIVAL_LIVES -
            answers.filter((a) => a.verdict === "incorrect").length,
        )
      : null;
  // Daily 20 only. The server snapshots the round's real term count at
  // creation (usually 20, but a smaller bank degrades to "however many
  // terms exist" — see daily_term_ids) — read from that response rather
  // than hard-coding 20 client-side, then counted down locally same as
  // livesRemaining.
  const [dailyTermCount, setDailyTermCount] = useState<number | null>(null);
  const termsRemaining =
    roundMode === "daily_20" && dailyTermCount !== null
      ? Math.max(0, dailyTermCount - answers.length)
      : null;
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
  const speech = useSpeechRecognition();
  const answerInputRef = useRef<HTMLTextAreaElement>(null);
  const sprintExpired = roundMode === "sprint" && remainingSeconds === 0;

  useEffect(() => {
    if (speech.transcript) setAnswer(speech.transcript);
  }, [speech.transcript]);

  useEffect(() => {
    const input = answerInputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  }, [answer]);

  // Exhaustive over RoundMode: a 6th mode added later is a type error here,
  // not a silently-wrong fallback branch.
  const ROUND_END: Record<RoundMode, boolean> = {
    classic: answers.length >= ROUND_LENGTH,
    sprint: sprintExpired,
    survival: livesRemaining === 0,
    boss: answers.length >= 1,
    daily_20: termsRemaining === 0,
  };
  const roundComplete = ROUND_END[roundMode];

  useEffect(() => {
    if (!term || result || roundComplete) speech.stop();
  }, [roundComplete, result, speech.stop, term]);

  useEffect(() => {
    const handleVoiceShortcut = (event: KeyboardEvent) => {
      const isVoiceShortcut =
        event.key.toLowerCase() === "m" &&
        event.shiftKey &&
        (event.ctrlKey || event.metaKey) &&
        !event.altKey;
      if (!isVoiceShortcut || !term || result || roundComplete || loading) {
        return;
      }
      event.preventDefault();
      speech.isListening ? speech.stop() : speech.start();
    };

    window.addEventListener("keydown", handleVoiceShortcut);
    return () => window.removeEventListener("keydown", handleVoiceShortcut);
  }, [
    loading,
    result,
    roundComplete,
    speech.isListening,
    speech.start,
    speech.stop,
    term,
  ]);

  const ROUND_END_HEADING: Record<RoundMode, string> = {
    classic: "round complete",
    sprint: "time's up",
    survival: "out of lives",
    boss: "boss round complete",
    daily_20: "daily 20 complete",
  };

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
  // fixed by the selectedMode picker at the moment the round starts;
  // category likewise locks in selectedCategory as roundCategory.
  const startRound = async () => {
    setError(null);
    setRoundCategory(selectedCategory);
    const { data } = await createRoundGameRoundsPost({
      body: { mode: selectedMode },
    });
    if (!data) {
      setError({ message: "Could not start a round.", retryAction: "load" });
      return;
    }
    setRoundId(data.id);
    // Trust the server's mode directly — RoundResponse.mode is typed as a
    // RoundMode, not a plain string, so this is no longer a lossy narrowing.
    setRoundMode(data.mode as RoundMode);
    setServerRemaining(data.remaining_seconds ?? null);
    setDailyTermCount(data.terms_remaining ?? null);
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
    // roundComplete: don't fire a submit the server would 422 anyway — the
    // round's own terminal state (Sprint's timer, Survival's lives, ...)
    // already flips to its end screen below.
    if (!term || !answer.trim() || !roundId || roundComplete) return;
    speech.stop();
    setLoading(true);
    setError(null);
    // Boss mode forces LLM grading server-side regardless of what's sent
    // (RoundMode.resolve_llm_grading) — the checkbox is hidden for it (see
    // the pre-submit form below), so this is what actually decides whether
    // the client takes the streaming path and shows the live rationale.
    const effectiveLlmGrading = roundMode === "boss" || useLlmGrading;
    setRequestedLlmGrading(effectiveLlmGrading);

    if (effectiveLlmGrading) {
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

        {/* Mode is fixed server-side at round creation — the picker only
            affects the round about to start, so it's shown before start
            and again once a round ends (via RoundSummary's "play again"),
            never mid-round. */}
        {!started && (
          <div className="bg-surface border border-surface-border p-6 space-y-4 text-center">
            <ModePicker selected={selectedMode} onChange={setSelectedMode} />
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
        {started && !roundComplete && roundMode === "survival" && (
          <p className="text-sm text-text-dim text-center">
            <span aria-hidden="true">
              {"♥".repeat(livesRemaining ?? 0)}
              {"♡".repeat(SURVIVAL_LIVES - (livesRemaining ?? 0))}
            </span>
            {/* aria-live: unlike the countdown, this changes once per
                answer, not per frame — worth announcing, not spam. */}
            <span className="sr-only" aria-live="polite">
              {livesRemaining ?? 0} lives remaining
            </span>
          </p>
        )}
        {started && !roundComplete && roundMode === "daily_20" && (
          <p className="text-sm text-text-dim text-center">
            term {Math.min(answers.length + 1, dailyTermCount ?? 20)}/
            {dailyTermCount ?? 20}
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
            <div className="flex items-start gap-2 bg-surface border border-surface-border px-4 py-3 focus-within:border-phosphor">
              <span className="text-phosphor select-none">&gt;</span>
              <textarea
                ref={answerInputRef}
                autoFocus
                rows={2}
                maxLength={512}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    submitAnswer();
                  }
                }}
                placeholder="type your answer…"
                className="max-h-40 min-h-12 w-full resize-none overflow-y-auto bg-transparent text-text placeholder:text-text-muted focus:outline-none"
              />
              <button
                type="button"
                onClick={() =>
                  speech.isListening ? speech.stop() : speech.start()
                }
                disabled={!speech.isSupported || loading}
                aria-label={
                  speech.isListening
                    ? "Stop voice input"
                    : "Start voice input"
                }
                aria-pressed={speech.isListening}
                title={
                  speech.isSupported
                    ? speech.isListening
                      ? "Stop voice input"
                      : "Start voice input"
                    : "Voice input is unavailable in this browser"
                }
                className="shrink-0 text-text-muted hover:text-phosphor disabled:cursor-not-allowed disabled:opacity-40"
              >
                {speech.isListening ? <MicOff size={18} /> : <Mic size={18} />}
              </button>
              <kbd className="hidden text-[10px] text-text-muted sm:inline">
                Ctrl/Cmd+Shift+M
              </kbd>
            </div>
            <div className="flex items-center justify-between text-xs text-text-muted">
              <span>Enter = new line</span>
              <span>
                <kbd>Ctrl/Cmd+Enter</kbd> = submit · {answer.length}/512
              </span>
            </div>
            <p className="min-h-5 text-xs text-text-muted" aria-live="polite">
              {speech.error ??
                (speech.isListening
                  ? "listening... speak your answer"
                  : !speech.isSupported
                    ? "voice input unavailable in this browser"
                    : "")}
            </p>
            {/* Boss mode forces LLM grading server-side — an unchecked,
                ignorable checkbox here would misrepresent what actually
                happens, so it's replaced with a plain statement of fact. */}
            {roundMode === "boss" ? (
              <p className="text-sm text-text-dim">
                AI grading is always on for boss rounds.
              </p>
            ) : (
              <label className="flex items-center gap-2 text-sm text-text-dim">
                <input
                  type="checkbox"
                  checked={useLlmGrading}
                  onChange={(e) => setUseLlmGrading(e.target.checked)}
                  className="accent-phosphor bg-surface border-surface-border"
                />
                get AI feedback on ambiguous answers
              </label>
            )}
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
            isBossRound={roundMode === "boss"}
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
            heading={ROUND_END_HEADING[roundMode]}
            selectedMode={selectedMode}
            onModeChange={setSelectedMode}
            onPlayAgain={startNewRound}
          />
        )}
      </main>
    </div>
  );
}
