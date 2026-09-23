import type { GameConfigResponse, RoundMode } from "./client";

// Hand-rolled: exactly one query today (ADR-0010), not enough surface to
// justify a GraphQL client library. Requests only gameConfig and
// termCategories — sessionScreen.randomTerm takes no round_id, so it can't
// replace startRound's loadTerm() call, which needs one for exclusion.
const SESSION_SCREEN_QUERY = `
  query SessionScreen {
    sessionScreen {
      gameConfig {
        modes { mode maxAnswers timed llmGrading }
        sprint {
          defaultDurationSeconds
          minDurationSeconds
          maxDurationSeconds
          durationOptionsSeconds
        }
        survivalLives
        dailyTermCount
        answerMaxLength
        scoreMax
        rubric { concept expansion purpose example }
      }
      termCategories
    }
  }
`;

type SessionScreenGameConfig = {
  modes: {
    mode: RoundMode;
    maxAnswers: number | null;
    timed: boolean;
    llmGrading: string;
  }[];
  sprint: {
    defaultDurationSeconds: number;
    minDurationSeconds: number;
    maxDurationSeconds: number;
    durationOptionsSeconds: number[];
  };
  survivalLives: number;
  dailyTermCount: number;
  answerMaxLength: number;
  scoreMax: number;
  rubric: { concept: number; expansion: number; purpose: number; example: number };
};

type SessionScreenData = {
  sessionScreen: {
    gameConfig: SessionScreenGameConfig;
    termCategories: string[];
  };
};

// GameConfig fields already match GameConfigResponse's shape except casing
// (camelCase over the wire vs. snake_case from the REST client) and mode
// (GraphQL's RoundMode mirror is lowercase-named to match REST — see
// api/graphql/types.py — so no further conversion is needed there).
function toGameConfigResponse(config: SessionScreenGameConfig): GameConfigResponse {
  return {
    modes: config.modes.map((m) => ({
      mode: m.mode,
      max_answers: m.maxAnswers,
      timed: m.timed,
      llm_grading: m.llmGrading,
    })),
    sprint: {
      default_duration_seconds: config.sprint.defaultDurationSeconds,
      min_duration_seconds: config.sprint.minDurationSeconds,
      max_duration_seconds: config.sprint.maxDurationSeconds,
      duration_options_seconds: config.sprint.durationOptionsSeconds,
    },
    survival_lives: config.survivalLives,
    daily_term_count: config.dailyTermCount,
    answer_max_length: config.answerMaxLength,
    score_max: config.scoreMax,
    rubric: config.rubric,
  };
}

export type SessionScreenResult = {
  gameConfig: GameConfigResponse;
  categories: string[];
};

// Aggregates GET /game-config + GET /terms/categories into one round trip.
// Returns null on any failure (network, GraphQL error, malformed body) —
// callers already treat a missing config/categories as non-fatal (client-side
// fallback constants, an empty category picker), so this mirrors that.
export async function fetchSessionScreen(): Promise<SessionScreenResult | null> {
  try {
    const response = await fetch("/graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: SESSION_SCREEN_QUERY }),
    });
    if (!response.ok) return null;

    const body = (await response.json()) as {
      data?: SessionScreenData;
      errors?: unknown[];
    };
    if (!body.data || body.errors?.length) return null;

    const { gameConfig, termCategories } = body.data.sessionScreen;
    return {
      gameConfig: toGameConfigResponse(gameConfig),
      categories: termCategories,
    };
  } catch {
    return null;
  }
}
