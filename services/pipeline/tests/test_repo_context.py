"""Tests for grep-based repo context gathering."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline_service.repo_context import find_usage_snippets


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=path, check=True
    )
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, check=True)


def test_find_usage_snippets_returns_matches(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "app.py").write_text("import fastapi\napp = fastapi.FastAPI()\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    snippets = find_usage_snippets("fastapi", tmp_path)

    assert len(snippets) >= 1
    assert "fastapi" in snippets[0].lower()


def test_find_usage_snippets_returns_empty_for_no_matches(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "app.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    snippets = find_usage_snippets("nonexistent-package-xyz", tmp_path)

    assert snippets == ()


def test_find_usage_snippets_respects_gitignore(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("ignored/\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "file.py").write_text("import fastapi\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    snippets = find_usage_snippets("fastapi", tmp_path)

    assert snippets == ()


def test_find_usage_snippets_caps_at_max_snippets(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    for i in range(10):
        (tmp_path / f"file{i}.py").write_text(f"import fastapi  # use {i}\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    snippets = find_usage_snippets("fastapi", tmp_path, max_snippets=3)

    assert len(snippets) == 3


def test_find_usage_snippets_rejects_non_identifier_names(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "app.py").write_text("import fastapi\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    # Not a valid package/import name shape - fast-fails rather than
    # running git grep with an unvalidated pattern.
    snippets = find_usage_snippets("fastapi; rm -rf /", tmp_path)

    assert snippets == ()


def test_find_usage_snippets_handles_a_non_git_directory(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import fastapi\n")

    snippets = find_usage_snippets("fastapi", tmp_path)

    assert snippets == ()
