"""Tests for document intake's format registry (ADR-0018)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import docx
import pypdf.errors

from pipeline_service.document_ingestion.document_sources import DocxSource
from pipeline_service.document_ingestion.document_sources import PdfSource
from pipeline_service.document_ingestion.document_sources import PlainTextSource
from pipeline_service.document_ingestion.document_sources import (
    extract_text_from_document,
)
from pipeline_service.document_ingestion.document_sources import find_intake_documents


def _fake_page(text: str, contents: MagicMock | None = None) -> MagicMock:
    page = MagicMock()
    page.extract_text.return_value = text
    page.get_contents.return_value = contents
    return page


def _fake_reader(*pages: MagicMock) -> MagicMock:
    reader = MagicMock()
    reader.pages = list(pages)
    return reader


def test_find_intake_documents_only_registered_formats(tmp_path: Path) -> None:
    intake = tmp_path / "intake" / "documents"
    intake.mkdir(parents=True)
    (intake / "contract.pdf").write_bytes(b"%PDF-1.4")
    (intake / "notes.md").write_text("some notes")
    (intake / "image.png").write_bytes(b"\x89PNG")
    docx.Document().save(str(intake / "report.docx"))

    found = find_intake_documents(intake)

    assert found == (
        intake / "contract.pdf",
        intake / "notes.md",
        intake / "report.docx",
    )


def test_find_intake_documents_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert find_intake_documents(tmp_path / "does-not-exist") == ()


def test_extract_text_from_document_dispatches_by_extension(tmp_path: Path) -> None:
    path = tmp_path / "readme.txt"
    path.write_text("plain text content")

    assert extract_text_from_document(path) == "plain text content"


def test_extract_text_from_document_unregistered_extension_yields_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG")

    assert extract_text_from_document(path) == ""


def test_plain_text_source_reads_the_file() -> None:
    source = PlainTextSource()
    assert source.extensions == (".txt", ".md")


def test_plain_text_source_yields_empty_on_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "binary.txt"
    path.write_bytes(b"\xff\xfe\x00\x01")  # invalid utf-8

    assert PlainTextSource().extract_text(path) == ""


def test_plain_text_source_yields_empty_when_missing(tmp_path: Path) -> None:
    assert PlainTextSource().extract_text(tmp_path / "missing.txt") == ""


def test_pdf_source_page_text_uses_text_layer_when_present() -> None:
    page = _fake_page("The MasterAgreement covers Vendor obligations.")

    assert (
        PdfSource()._page_text(page) == "The MasterAgreement covers Vendor obligations."
    )


def test_pdf_source_page_text_falls_back_to_ocr_when_layer_is_empty() -> None:
    page = _fake_page("")

    with patch(
        "pipeline_service.document_ingestion.document_sources.PdfSource._ocr_page",
        return_value="OCR'd text",
    ) as ocr:
        result = PdfSource()._page_text(page)

    ocr.assert_called_once_with(page)
    assert result == "OCR'd text"


def test_pdf_source_joins_pages(tmp_path: Path) -> None:
    path = tmp_path / "contract.pdf"
    path.write_bytes(b"%PDF-1.4")
    page_one = _fake_page("This is the first page's full text layer content.")
    page_two = _fake_page("This is the second page's full text layer content.")

    with patch("pypdf.PdfReader", return_value=_fake_reader(page_one, page_two)):
        text = PdfSource().extract_text(path)

    assert text == (
        "This is the first page's full text layer content.\n"
        "This is the second page's full text layer content."
    )


def test_pdf_source_skips_corrupt_pdf(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a real pdf")

    with patch("pypdf.PdfReader", side_effect=pypdf.errors.PdfReadError("bad file")):
        text = PdfSource().extract_text(path)

    assert text == ""


def test_docx_source_joins_paragraphs_in_order(tmp_path: Path) -> None:
    path = tmp_path / "contract.docx"
    document = docx.Document()
    document.add_paragraph("The MasterAgreement binds Vendor and Client.")
    document.add_paragraph("Payment terms are net thirty days.")
    document.save(str(path))

    text = DocxSource().extract_text(path)

    assert text == (
        "The MasterAgreement binds Vendor and Client.\n"
        "Payment terms are net thirty days."
    )


def test_docx_source_empty_document_yields_empty_text(tmp_path: Path) -> None:
    path = tmp_path / "empty.docx"
    docx.Document().save(str(path))

    assert DocxSource().extract_text(path) == ""


def test_docx_source_skips_a_missing_file(tmp_path: Path) -> None:
    assert DocxSource().extract_text(tmp_path / "missing.docx") == ""


def test_docx_source_skips_a_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a real docx")

    assert DocxSource().extract_text(path) == ""
