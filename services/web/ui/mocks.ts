import type { Page } from "@playwright/test";

/**
 * A fixed pool of terms, cycled deterministically (no real randomness) so
 * a test can assert exactly which term appears next.
 */
const TERMS = [
  { id: "uow", term: "UoW" },
  { id: "cqrs", term: "CQRS" },
  { id: "cap-theorem", term: "CAP Theorem" },
];

export type GradeRule = (answer: string) => {
  verdict: "correct" | "partial" | "incorrect";
  score: number;
};

// Default: any non-empty answer grades CORRECT. Tests override via
// mockBackend's gradeRule param for partial/incorrect scenarios.
const defaultGradeRule: GradeRule = () => ({ verdict: "correct", score: 30 });

/**
 * Installs route mocks for every endpoint App.tsx calls: the sessionScreen
 * GraphQL query, POST /game-rounds, GET /terms/random, POST
 * .../answers/submit (and its /stream variant). No real
 * game-service/Postgres involved — this is a frontend state-machine test,
 * not a full-stack one (see playwright.config.ts).
 */
export async function mockBackend(
  page: Page,
  options: {
    gradeRule?: GradeRule;
    // A fixed duration for every sprint round, or a function of the
    // 1-indexed round number for tests that need round N's duration to
    // differ from round N+1's (e.g. proving play-again re-syncs the
    // countdown rather than reusing the expired round's value).
    sprintDurationSeconds?: number | ((roundNumber: number) => number);
    // Empty by default (see the /terms/categories mock below) — a test
    // exercising the picker itself overrides this.
    categories?: string[];
  } = {},
): Promise<{
  lastRandomTermCategory: () => string | null;
  lastRandomTermDifficulty: () => string | null;
  lastRoundRequest: () => {
    mode?: "classic" | "sprint" | "survival" | "boss" | "daily_20";
    duration_seconds?: number;
  } | null;
}> {
  const gradeRule = options.gradeRule ?? defaultGradeRule;
  const sprintDuration =
    typeof options.sprintDurationSeconds === "function"
      ? options.sprintDurationSeconds
      : () => options.sprintDurationSeconds ?? 60;
  const categories = options.categories ?? [];
  let roundCounter = 0;
  let termIndex = 0;
  let lastRandomTermCategory: string | null = null;
  let lastRandomTermDifficulty: string | null = null;
  let lastRoundRequest: {
    mode?: "classic" | "sprint" | "survival" | "boss" | "daily_20";
    duration_seconds?: number;
  } | null = null;

  // App.tsx fetches gameConfig + termCategories through one sessionScreen
  // GraphQL query (ADR-0010), not the REST /game-config and
  // /terms/categories endpoints — mock that query instead of those routes.
  await page.route("**/graphql", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          sessionScreen: {
            gameConfig: {
              modes: [
                { mode: "classic", maxAnswers: 200, timed: false, llmGrading: "optional" },
                { mode: "sprint", maxAnswers: null, timed: true, llmGrading: "disabled" },
                { mode: "survival", maxAnswers: null, timed: false, llmGrading: "optional" },
                { mode: "boss", maxAnswers: 1, timed: false, llmGrading: "forced" },
                { mode: "daily_20", maxAnswers: 20, timed: false, llmGrading: "disabled" },
              ],
              sprint: {
                defaultDurationSeconds: 60,
                minDurationSeconds: 10,
                maxDurationSeconds: 300,
                durationOptionsSeconds: [10, 30, 60, 120, 300],
              },
              survivalLives: 3,
              dailyTermCount: 20,
              answerMaxLength: 512,
              scoreMax: 100,
              rubric: { concept: 40, expansion: 30, purpose: 20, example: 10 },
            },
            termCategories: categories,
          },
        },
      }),
    });
  });

  await page.route("**/game-rounds", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as {
      mode?: "classic" | "sprint" | "survival" | "boss" | "daily_20";
      duration_seconds?: number;
    } | null;
    lastRoundRequest = body;
    roundCounter += 1;
    termIndex = 0;
    const mode = body?.mode ?? "classic";
    const isSprint = mode === "sprint";
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: `round-${roundCounter}`,
        created_at: new Date().toISOString(),
        answers: [],
        mode,
        remaining_seconds: isSprint
          ? options.sprintDurationSeconds !== undefined
            ? sprintDuration(roundCounter)
            : body?.duration_seconds ?? 60
          : null,
        is_over: false,
        lives_remaining: mode === "survival" ? 3 : null,
        terms_remaining: mode === "daily_20" ? 20 : null,
      }),
    });
  });

  await page.route("**/terms/random**", async (route) => {
    const url = new URL(route.request().url());
    lastRandomTermCategory = url.searchParams.get("category");
    lastRandomTermDifficulty = url.searchParams.get("difficulty");
    const term = TERMS[termIndex % TERMS.length];
    termIndex += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(term),
    });
  });

  await page.route("**/answers/submit", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as { answer: string };
    const { verdict, score } = gradeRule(body.answer);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        verdict,
        matched_via: verdict === "correct" ? "exact" : "fuzzy",
        confidence: verdict === "correct" ? 1.0 : 0.5,
        score,
        feedback: "mock feedback",
        rubric: {
          concept: 0,
          expansion: score,
          purpose: 0,
          example: 0,
          total: score,
        },
      }),
    });
  });

  // Boss mode's client always takes the streaming path (see App.tsx's
  // effectiveLlmGrading). No rationale_delta frames — a single "graded"
  // event is a real, valid server response whenever the deterministic
  // verdict never reaches PARTIAL (nothing to stream), which is what this
  // mock's gradeRule always produces (CORRECT or a caller-forced verdict).
  await page.route("**/answers/submit/stream", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as { answer: string };
    const { verdict, score } = gradeRule(body.answer);
    const graded = {
      verdict,
      matched_via: verdict === "correct" ? "exact" : "fuzzy",
      confidence: verdict === "correct" ? 1.0 : 0.5,
      score,
      feedback: "mock feedback",
      rubric: {
        concept: 0,
        expansion: score,
        purpose: 0,
        example: 0,
        total: score,
      },
    };
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `event: graded\ndata: ${JSON.stringify(graded)}\n\n`,
    });
  });

  return {
    lastRandomTermCategory: () => lastRandomTermCategory,
    lastRandomTermDifficulty: () => lastRandomTermDifficulty,
    lastRoundRequest: () => lastRoundRequest,
  };
}
