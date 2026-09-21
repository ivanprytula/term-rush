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
ROUND_MAX_ANSWERS = 200  # generous ceiling; no game mode runs this long yet
