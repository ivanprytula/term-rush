"""Domain constants: bounds, weights, thresholds.

Single source of truth for all magic numbers. Changes here propagate to
validation, schemas, and tests automatically.
"""

# Term bounds
TERM_ID_MIN_LEN = 1
TERM_ID_MAX_LEN = 64
TERM_MIN_LEN = 1
TERM_MAX_LEN = 64
TERM_SLUG_MIN_LEN = 1
TERM_SLUG_MAX_LEN = 32
TERM_EXPANSION_MIN_LEN = 1
TERM_EXPANSION_MAX_LEN = 256
TERM_DEFINITION_MIN_LEN = 1
TERM_DEFINITION_MAX_LEN = 1024
TERM_PRIMARY_DEFINITION_MIN_LEN = 40  # Boss-eligible terms require ≥40 chars

# Answer bounds
ANSWER_MIN_LEN = 1
ANSWER_MAX_LEN = 512

# Rubric weights (sum = 100), heaviest first
CONCEPT_WEIGHT = 40
EXPANSION_WEIGHT = 30
PURPOSE_WEIGHT = 20
EXAMPLE_WEIGHT = 10

# Score bounds
MIN_SCORE = 0
MAX_SCORE = 100

# Confidence bounds
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0

# Grading thresholds (Phase 1 deterministic chain)
FUZZY_MATCH_THRESHOLD = 0.62  # ADR-0002: substring match passes at 0.62

# Scheduling / review priority
RECENT_WINDOW_DAYS = 7  # How long a term stays "recent" after first introduction

# Round bounds
ROUND_ID_MAX_LEN = 64
ROUND_MAX_ANSWERS = 200  # generous ceiling; tightest real cap is DAILY_20_ROUND_SIZE=20

# Sprint mode
DEFAULT_SPRINT_DURATION_SECONDS = 60
MIN_SPRINT_DURATION_SECONDS = 10
MAX_SPRINT_DURATION_SECONDS = 300

# Survival mode
SURVIVAL_LIVES = 3  # one lost per INCORRECT verdict; PARTIAL/CORRECT are free

# Boss Round
BOSS_ROUND_SIZE = 1  # a Boss round is exactly one term, one answer

# Daily 20
DAILY_20_ROUND_SIZE = 20  # first server-enforced term count; Classic's
# ROUND_LENGTH=10 is still client-only
DAILY_20_SEED_EPOCH = "term-rush-daily"  # namespace prefix for the date seed,
# so the same date in another feature
# can't produce the same ordering

# Leaderboard bounds
LEADERBOARD_MIN_LIMIT = 1
LEADERBOARD_MAX_LIMIT = 100
LEADERBOARD_DEFAULT_LIMIT = 10
