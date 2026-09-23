"""Tests for the dependency-manifest extractor."""

from __future__ import annotations

from pathlib import Path

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.extractors.dependency_manifest import extract_dependency_manifests
from pipeline_service.extractors.dependency_manifest import extract_from_pyproject
from pipeline_service.extractors.dependency_manifest import find_pyproject_files

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_find_pyproject_files_excludes_venv_and_node_modules(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyproject.toml").write_text("[project]\nname='y'\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pyproject.toml").write_text("[project]\nname='z'\n")

    found = find_pyproject_files(tmp_path)

    assert found == (tmp_path / "pyproject.toml",)


def test_extract_from_pyproject_strips_extras_and_specifiers(tmp_path: Path) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        '[project]\ndependencies = ["fastapi[standard]>=0.141.1,<1.0.0", "pydantic>=2.9"]\n'
    )

    candidates = extract_from_pyproject(manifest)

    names = {c.name for c in candidates}
    assert names == {"fastapi", "pydantic"}


def test_extract_from_pyproject_reads_dependency_groups(tmp_path: Path) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        "[project]\ndependencies = []\n"
        "[dependency-groups]\ndev = ['pytest>=8.3', 'ruff>=0.7']\n"
    )

    candidates = extract_from_pyproject(manifest)

    names = {c.name for c in candidates}
    assert names == {"pytest", "ruff"}


def test_extract_from_pyproject_excludes_workspace_packages(tmp_path: Path) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        '[project]\ndependencies = ["term-proto", "termrush-core", "fastapi"]\n'
    )

    candidates = extract_from_pyproject(manifest)

    names = {c.name for c in candidates}
    assert names == {"fastapi"}


def test_extract_from_pyproject_skips_invalid_requirement_strings(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        '[project]\ndependencies = ["not a valid==requirement!!", "fastapi"]\n'
    )

    candidates = extract_from_pyproject(manifest)

    names = {c.name for c in candidates}
    assert names == {"fastapi"}


def test_extract_from_pyproject_sets_provenance() -> None:
    manifest = REPO_ROOT / "services" / "content" / "pyproject.toml"

    candidates = extract_from_pyproject(manifest)

    assert candidates
    for candidate in candidates:
        assert candidate.source_type == SourceType.DEPENDENCY_MANIFEST
        assert candidate.confidence == Confidence.HIGH
        assert candidate.source_file == str(manifest)


def test_extract_dependency_manifests_covers_the_real_workspace() -> None:
    """End-to-end against the actual repo: proves the extractor produces
    real vocabulary (ADR-0004's dependency-manifest source), not just
    toy fixtures.
    """
    candidates = extract_dependency_manifests(REPO_ROOT)

    names = {c.name for c in candidates}
    assert "fastapi" in names
    assert "sqlalchemy" in names
    assert "dagster" in names
    # Workspace-internal packages must never surface as vocabulary.
    assert "term-proto" not in names
    assert "termrush-core" not in names


def test_extract_dependency_manifests_deduplicates_shared_dependencies() -> None:
    """pydantic appears in every service's manifest; it must yield one
    candidate, not one per occurrence.
    """
    candidates = extract_dependency_manifests(REPO_ROOT)

    names = [c.name for c in candidates]
    assert names.count("pydantic") == 1
