"""Format-agnostic document intake (ADR-0018, generalized per its own
"when I would change this" trigger: a second format is now genuinely
needed, not speculative).

Everything downstream of extraction - chunking, the document_chunks store,
RAG retrieval - already works on plain (source_file, text) pairs with zero
PDF-specific assumptions. The only place format leaked in was here: finding
intake files and turning one into text. A DocumentSource per format,
dispatched by extension, keeps that the only place a new format has to
touch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import docx
import docx.opc.exceptions
import pypdf
import pypdf.errors

_MIN_TEXT_LAYER_CHARS = 20  # below this, treat a PDF page as scanned


class DocumentSource(Protocol):
    """One intake format: which files it claims, how to read their text."""

    extensions: tuple[str, ...]

    def extract_text(self, path: Path) -> str:
        """The document's full text. A corrupt/unreadable file yields
        empty text rather than raising - one bad file shouldn't fail
        extraction for the whole intake directory."""
        ...


class PlainTextSource:
    """.txt/.md files: no extraction, the file already is the text."""

    extensions = (".txt", ".md")

    def extract_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            return ""


class DocxSource:
    """.docx files: paragraph text, joined in document order. No table/
    header/footer extraction yet — plain body paragraphs cover the common
    case (a written contract or report); tables are a real gap, not a
    silent one, if that content type shows up in the intake directory.
    """

    extensions = (".docx",)

    def extract_text(self, path: Path) -> str:
        try:
            document = docx.Document(str(path))
        except docx.opc.exceptions.PackageNotFoundError:
            return ""
        return "\n".join(p.text for p in document.paragraphs)


class PdfSource:
    """PDFs: pypdf's text-layer extraction first, OCR fallback per page for
    scanned content. Deterministic, no LLM (ADR-0004's Extract stage) -
    provenance has to mean "mechanically pulled from page N," not "the
    model said so" (see ADR-0018's "why classical OCR, not a vision-LLM").
    """

    extensions = (".pdf",)

    def extract_text(self, path: Path) -> str:
        try:
            reader = pypdf.PdfReader(path)
        except pypdf.errors.PdfReadError, OSError:
            return ""
        return "\n".join(self._page_text(page) for page in reader.pages)

    def _page_text(self, page: pypdf.PageObject) -> str:
        text = page.extract_text()
        if len(text.strip()) >= _MIN_TEXT_LAYER_CHARS:
            return text
        return self._ocr_page(page)

    def _ocr_page(
        self, page: pypdf.PageObject
    ) -> str:  # pragma: no cover - needs tesseract
        """Render a scanned page to an image and OCR it.

        Imported lazily: pytesseract/pdf2image need system binaries
        (tesseract-ocr, poppler-utils) this repo doesn't assume are present
        everywhere the text-layer path is exercised (e.g. CI running unit
        tests against text-layer fixtures only).
        """
        import pdf2image
        import pytesseract

        contents = page.get_contents()
        if contents is None:
            return ""
        images = pdf2image.convert_from_bytes(contents.get_data())
        return "\n".join(pytesseract.image_to_string(image) for image in images)


# Registration point for a new format: add the DocumentSource here. Nothing
# else in document_ingestion/ needs to change - chunking, the Dagster
# assets, and content-service's chunk store already work on plain text.
_SOURCES: tuple[DocumentSource, ...] = (PdfSource(), PlainTextSource(), DocxSource())

_BY_EXTENSION: dict[str, DocumentSource] = {
    ext: source for source in _SOURCES for ext in source.extensions
}


def find_intake_documents(intake_dir: Path) -> tuple[Path, ...]:
    """Every file in a registered format in the intake directory, sorted
    for deterministic ordering."""
    if not intake_dir.is_dir():
        return ()
    return tuple(
        sorted(
            path
            for path in intake_dir.iterdir()
            if path.suffix.lower() in _BY_EXTENSION
        )
    )


def extract_text_from_document(path: Path) -> str:
    """A document's full text, dispatched to the source registered for its
    extension. An unregistered extension yields empty text - the same
    "one bad file doesn't fail the batch" contract each source itself
    honors for its own failures."""
    source = _BY_EXTENSION.get(path.suffix.lower())
    if source is None:
        return ""
    return source.extract_text(path)
