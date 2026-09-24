"""Tests for the document/OCR term-candidate extractor (ADR-0018,
secondary consumer of document ingestion - see test_document_text.py for
the shared OCR mechanics).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.document_ingestion.extractors.document_ocr import (
    extract_document_sources,
)
from pipeline_service.document_ingestion.extractors.document_ocr import (
    extract_from_document,
)


def _fake_page(text: str) -> MagicMock:
    page = MagicMock()
    page.extract_text.return_value = text
    return page


def _fake_reader(*pages: MagicMock) -> MagicMock:
    reader = MagicMock()
    reader.pages = list(pages)
    return reader


def test_extract_from_document_pulls_capitalized_tokens(tmp_path: Path) -> None:
    path = tmp_path / "contract.pdf"
    path.write_bytes(b"%PDF-1.4")
    page = _fake_page("This MasterAgreement binds Vendor and Client.")

    with patch("pypdf.PdfReader", return_value=_fake_reader(page)):
        candidates = extract_from_document(path)

    names = {c.name for c in candidates}
    assert names == {"MasterAgreement", "Vendor", "Client"}


def test_extract_from_document_sets_provenance(tmp_path: Path) -> None:
    path = tmp_path / "contract.pdf"
    path.write_bytes(b"%PDF-1.4")
    page = _fake_page("MasterAgreement terms.")

    with patch("pypdf.PdfReader", return_value=_fake_reader(page)):
        candidates = extract_from_document(path)

    assert candidates
    for candidate in candidates:
        assert candidate.source_type == SourceType.DOCUMENT_OCR
        assert candidate.confidence == Confidence.LOW
        assert candidate.source_file == str(path)


def test_extract_from_document_dedupes_within_one_file(tmp_path: Path) -> None:
    path = tmp_path / "contract.pdf"
    path.write_bytes(b"%PDF-1.4")
    page = _fake_page("MasterAgreement terms apply. MasterAgreement governs disputes.")

    with patch("pypdf.PdfReader", return_value=_fake_reader(page)):
        candidates = extract_from_document(path)

    assert len(candidates) == 1


def test_extract_document_sources_deduplicates_across_files(tmp_path: Path) -> None:
    intake = tmp_path
    (intake / "a.pdf").write_bytes(b"%PDF-1.4")
    (intake / "b.pdf").write_bytes(b"%PDF-1.4")

    page_a = _fake_page("MasterAgreement in file A.")
    page_b = _fake_page("MasterAgreement in file B.")
    readers = {
        str(intake / "a.pdf"): _fake_reader(page_a),
        str(intake / "b.pdf"): _fake_reader(page_b),
    }

    def fake_reader(path: Path) -> MagicMock:
        return readers[str(path)]

    with patch("pypdf.PdfReader", side_effect=fake_reader):
        candidates = extract_document_sources(intake)

    names = [c.name for c in candidates]
    assert names.count("MasterAgreement") == 1
    assert candidates[0].source_file == str(intake / "a.pdf")


@pytest.mark.parametrize("intake_dir_name", ["missing"])
def test_extract_document_sources_empty_intake_dir(
    tmp_path: Path, intake_dir_name: str
) -> None:
    assert extract_document_sources(tmp_path / intake_dir_name) == ()
