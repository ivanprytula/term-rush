"""Domain constants: term bounds.

Single source of truth for content-service's magic numbers. Changes here
propagate to validation, schemas, and tests automatically.
"""

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
