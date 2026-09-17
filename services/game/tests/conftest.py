import os
from pathlib import Path

# Hypothesis has no pyproject setting for this; it reads the env var at import.
os.environ.setdefault(
    "HYPOTHESIS_STORAGE_DIRECTORY",
    str(Path(__file__).resolve().parents[3] / ".cache" / "hypothesis"),
)
