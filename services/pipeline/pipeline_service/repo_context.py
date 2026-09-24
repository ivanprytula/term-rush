"""Grep-based grounding for enrich: real usages of a candidate name in
this repo, so the LLM drafts an example that cites this codebase instead
of inventing a generic one.

Deliberately not RAG (no embeddings, no vector search) — proportional to
today's scale (a few dozen candidates). ADR-0012 covers pgvector for the
document-ingestion corpus, which reached embeddable scale/shape; this
term-candidate corpus hasn't and stays on grep grounding until it does.

Kept deliberately small: a dependency-manifest candidate (fastapi, httpx,
sqlalchemy, ...) is a well-known public package the model already knows
what it is — grounding earns its cost only for the example field ("what
does *this* repo do with it"), not for expansion/definition. No context
lines, a tight snippet cap, and each line capped in length, so this adds
a handful of short lines to the prompt, not a wall of text.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

MAX_SNIPPETS = 2
MAX_LINE_LEN = 160


def find_usage_snippets(
    name: str, repo_root: Path, max_snippets: int = MAX_SNIPPETS
) -> tuple[str, ...]:
    """Grep the repo for literal occurrences of `name`, returning up to
    max_snippets single lines (path:line:match, no surrounding context).

    Uses git grep (respects .gitignore, so .venv/node_modules/build
    output never leak in) rather than the stdlib — this repo is always
    a git checkout, and re-implementing gitignore-aware traversal isn't
    worth it for a grounding step.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", name):
        # Anything else can't be a real package/import name anyway, and
        # git grep -F treats it literally so this is purely a fast-fail.
        return ()

    grep_command = [
        "git",
        "grep",
        "--fixed-strings",
        "--ignore-case",
        "--line-number",
        "--",
        name,
    ]
    try:
        result = subprocess.run(
            grep_command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return ()
    except FileNotFoundError:
        return ()

    if result.returncode not in (0, 1):  # 1 = no matches, not an error
        return ()

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return tuple(line[:MAX_LINE_LEN] for line in lines[:max_snippets])
