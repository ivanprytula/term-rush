"""Tests for the class/Protocol-name extractor."""

from __future__ import annotations

from pathlib import Path

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.extractors.class_names import extract_class_names
from pipeline_service.extractors.class_names import extract_from_file
from pipeline_service.extractors.class_names import find_source_files

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_service_tree(tmp_path: Path) -> Path:
    pkg = tmp_path / "services" / "example" / "game_service"
    pkg.mkdir(parents=True)
    return pkg


def test_find_source_files_excludes_api_tests_and_alembic(tmp_path: Path) -> None:
    pkg = _make_service_tree(tmp_path)
    (pkg / "domain.py").write_text("class Kept:\n    '''doc'''\n")
    (pkg / "api").mkdir()
    (pkg / "api" / "schemas.py").write_text("class Skipped:\n    '''doc'''\n")
    (pkg / "tests").mkdir()
    (pkg / "tests" / "test_x.py").write_text("class AlsoSkipped:\n    '''doc'''\n")

    found = find_source_files(tmp_path)

    assert (pkg / "domain.py") in found
    assert not any("api" in f.parts for f in found)
    assert not any("tests" in f.parts for f in found)


def test_find_source_files_excludes_generated_protobuf_stubs(tmp_path: Path) -> None:
    pkg = tmp_path / "libs" / "term-proto" / "src" / "term_proto"
    pkg.mkdir(parents=True)
    (pkg / "term_pb2.py").write_text("class Generated:\n    '''doc'''\n")
    (pkg / "term_pb2_grpc.py").write_text("class AlsoGenerated:\n    '''doc'''\n")

    found = find_source_files(tmp_path)

    assert found == ()


def test_extract_from_file_takes_documented_classes_only(tmp_path: Path) -> None:
    module = tmp_path / "example.py"
    module.write_text(
        "class Documented:\n"
        "    '''Has a docstring.'''\n\n"
        "class Undocumented:\n"
        "    pass\n"
    )

    candidates = extract_from_file(module)

    names = {c.name for c in candidates}
    assert names == {"Documented"}


def test_extract_from_file_skips_private_classes(tmp_path: Path) -> None:
    module = tmp_path / "example.py"
    module.write_text(
        "class _Private:\n    '''Has a docstring.'''\n\nclass Public:\n    '''Also.'''\n"
    )

    candidates = extract_from_file(module)

    names = {c.name for c in candidates}
    assert names == {"Public"}


def test_extract_from_file_skips_files_with_syntax_errors(tmp_path: Path) -> None:
    module = tmp_path / "broken.py"
    module.write_text("class Broken(:\n")

    candidates = extract_from_file(module)

    assert candidates == ()


def test_extract_from_file_dedupes_within_one_file(tmp_path: Path) -> None:
    module = tmp_path / "example.py"
    module.write_text(
        "class Repeated:\n    '''First.'''\n\nclass Repeated:\n    '''Second.'''\n"
    )

    candidates = extract_from_file(module)

    assert len(candidates) == 1


def test_extract_from_file_sets_provenance(tmp_path: Path) -> None:
    module = tmp_path / "example.py"
    module.write_text("class Documented:\n    '''Has a docstring.'''\n")

    candidates = extract_from_file(module)

    assert candidates
    for candidate in candidates:
        assert candidate.source_type == SourceType.CLASS_NAME
        assert candidate.confidence == Confidence.MEDIUM
        assert candidate.source_file == str(module)


def test_extract_class_names_covers_the_real_repo() -> None:
    """End-to-end against the actual repo: proves the extractor produces
    real vocabulary, not just toy fixtures.
    """
    candidates = extract_class_names(REPO_ROOT)

    names = {c.name for c in candidates}
    assert "UnitOfWork" in names
    assert "Grader" in names
    assert "AnswerEvaluator" in names
    # Transport DTOs under api/ must never surface as vocabulary.
    assert "CreateRoundRequest" not in names
    assert "GameConfigResponse" not in names
    # Generated protobuf stubs must never surface as vocabulary.
    assert "TermServiceServicer" not in names


def test_extract_class_names_deduplicates_across_files() -> None:
    """`UnitOfWork` is defined in both game_service and content_service;
    it must yield one candidate, not one per occurrence.
    """
    candidates = extract_class_names(REPO_ROOT)

    names = [c.name for c in candidates]
    assert names.count("UnitOfWork") == 1
