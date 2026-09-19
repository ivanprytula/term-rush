import { useEffect, useState } from "react";
import {
  getRandomTermTermsRandomGet,
  submitAnswerSessionsSessionIdAnswersSubmitPost,
} from "./client";
import type { SubmitAnswerResponse, TermPromptResponse } from "./client";

const SESSION_ID_KEY = "term-rush-session-id";

function getOrCreateSessionId(): string {
  const existing = localStorage.getItem(SESSION_ID_KEY);
  if (existing) return existing;
  const created = crypto.randomUUID();
  localStorage.setItem(SESSION_ID_KEY, created);
  return created;
}

function verdictColor(verdict: string): string {
  if (verdict === "correct") return "text-green-400";
  if (verdict === "partial") return "text-yellow-400";
  return "text-red-400";
}

export default function App() {
  const [sessionId] = useState(getOrCreateSessionId);
  const [term, setTerm] = useState<TermPromptResponse | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<SubmitAnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTerm = async () => {
    setError(null);
    setResult(null);
    setAnswer("");
    const { data, error } = await getRandomTermTermsRandomGet();
    if (error) {
      setError("Could not load a term. Is the term bank seeded?");
      return;
    }
    setTerm(data ?? null);
  };

  useEffect(() => {
    loadTerm();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!term || !answer.trim()) return;
    setLoading(true);
    setError(null);
    const { data, error } = await submitAnswerSessionsSessionIdAnswersSubmitPost({
      path: { session_id: sessionId },
      body: { term_id: term.id, answer },
    });
    setLoading(false);
    if (error) {
      setError("Grading failed. Try again.");
      return;
    }
    setResult(data ?? null);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6">
        <h1 className="text-2xl font-bold tracking-tight text-center">
          Term Rush
        </h1>

        {error && <p className="text-red-400 text-sm text-center">{error}</p>}

        {term && !result && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 text-center">
              <p className="text-sm text-slate-400 mb-1">Define this term:</p>
              <p className="text-3xl font-bold">{term.term}</p>
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
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 space-y-3">
            <p className={`text-xl font-bold ${verdictColor(result.verdict)}`}>
              {result.verdict.toUpperCase()} · {result.score}/100
            </p>
            <p className="text-slate-300 text-sm">{result.feedback}</p>
            <button
              onClick={loadTerm}
              className="w-full rounded-lg bg-slate-700 hover:bg-slate-600 px-4 py-3 font-medium transition"
            >
              Next term
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
