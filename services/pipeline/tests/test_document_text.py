"""Tests for shared document OCR mechanics (ADR-0018)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pypdf.errors

from pipeline_service.document_ingestion.document_text import _page_text
from pipeline_service.document_ingestion.document_text import extract_text_from_document
from pipeline_service.document_ingestion.document_text import find_intake_documents


def _fake_page(text: str, contents: MagicMock | None = None) -> MagicMock:
    page = MagicMock()
    page.extract_text.return_value = text
    page.get_contents.return_value = contents
    return page


def _fake_reader(*pages: MagicMock) -> MagicMock:
    reader = MagicMock()
    reader.pages = list(pages)
    return reader


def test_find_intake_documents_only_pdfs(tmp_path: Path) -> None:
    intake = tmp_path / "docs" / "source-documents"
    intake.mkdir(parents=True)
    (intake / "contract.pdf").write_bytes(b"%PDF-1.4")
    (intake / "notes.txt").write_text("not a pdf")

    found = find_intake_documents(intake)

    assert found == (intake / "contract.pdf",)


def test_find_intake_documents_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert find_intake_documents(tmp_path / "does-not-exist") == ()


def test_page_text_uses_text_layer_when_present() -> None:
    page = _fake_page("The MasterAgreement covers Vendor obligations.")

    assert _page_text(page) == "The MasterAgreement covers Vendor obligations."


def test_page_text_falls_back_to_ocr_when_layer_is_empty() -> None:
    page = _fake_page("")

    with patch(
        "pipeline_service.document_ingestion.document_text._ocr_page",
        return_value="OCR'd text",
    ) as ocr:
        result = _page_text(page)

    ocr.assert_called_once_with(page)
    assert result == "OCR'd text"


def test_extract_text_from_document_joins_pages(tmp_path: Path) -> None:
    path = tmp_path / "contract.pdf"
    path.write_bytes(b"%PDF-1.4")
    page_one = _fake_page("This is the first page's full text layer content.")
    page_two = _fake_page("This is the second page's full text layer content.")

    with patch("pypdf.PdfReader", return_value=_fake_reader(page_one, page_two)):
        text = extract_text_from_document(path)

    assert text == (
        "This is the first page's full text layer content.\n"
        "This is the second page's full text layer content."
    )


def test_extract_text_from_document_skips_corrupt_pdf(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a real pdf")

    with patch("pypdf.PdfReader", side_effect=pypdf.errors.PdfReadError("bad file")):
        text = extract_text_from_document(path)

    assert text == ""
