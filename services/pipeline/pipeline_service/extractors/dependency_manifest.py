"""Extract candidate terms from pyproject.toml dependency lists.

Deterministic, no LLM (ADR-0004's Extract stage): parses PEP 508
requirement strings and emits one candidate per distribution name. A
manifest's own workspace-internal packages (term-proto, termrush-core,
pipeline-service itself) are excluded — they aren't vocabulary, they're
this repo's own code.
"""

from __future__ import annotations

from pathlib import Path

import tomlkit
from packaging.requirements import InvalidRequirement
from packaging.requirements import Requirement

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate

_WORKSPACE_PACKAGE_NAMES = frozenset(
    {
        "term-rush",
        "term-proto",
        "termrush-core",
        "content-service",
        "game-service",
        "pipeline-service",
    }
)


def find_pyproject_files(repo_root: Path) -> tuple[Path, ...]:
    """Every pyproject.toml in the workspace, excluding vendored/build dirs."""
    return tuple(
        sorted(
            p
            for p in repo_root.rglob("pyproject.toml")
            if ".venv" not in p.parts and "node_modules" not in p.parts
        )
    )


def _requirement_strings(document: tomlkit.TOMLDocument) -> tuple[str, ...]:
    """Every dependency string across [project.dependencies] and every
    group in [dependency-groups] — both are where this workspace's
    manifests declare real package names.
    """
    project = document.get("project", {})
    strings: list[str] = list(project.get("dependencies", []))

    groups = document.get("dependency-groups", {})
    for group_deps in groups.values():
        strings.extend(d for d in group_deps if isinstance(d, str))

    return tuple(strings)


def extract_from_pyproject(path: Path) -> tuple[TermCandidate, ...]:
    """Parse one pyproject.toml into candidates, one per distinct external
    dependency name. Malformed requirement strings are skipped, not
    fatal — one bad line shouldn't fail extraction for the whole file.
    """
    document = tomlkit.parse(path.read_text())
    candidates: dict[str, TermCandidate] = {}

    for raw in _requirement_strings(document):
        try:
            requirement = Requirement(raw)
        except InvalidRequirement:
            continue

        name = requirement.name
        if name in _WORKSPACE_PACKAGE_NAMES:
            continue

        candidates[name] = TermCandidate(
            name=name,
            source_type=SourceType.DEPENDENCY_MANIFEST,
            source_file=str(path),
            confidence=Confidence.HIGH,
        )

    return tuple(candidates.values())


def extract_dependency_manifests(repo_root: Path) -> tuple[TermCandidate, ...]:
    """Extract candidates from every pyproject.toml in the workspace,
    deduplicated by name (a dependency shared across services yields one
    candidate, keeping the first file it was seen in).
    """
    seen: dict[str, TermCandidate] = {}
    for path in find_pyproject_files(repo_root):
        for candidate in extract_from_pyproject(path):
            seen.setdefault(candidate.name, candidate)
    return tuple(seen.values())
