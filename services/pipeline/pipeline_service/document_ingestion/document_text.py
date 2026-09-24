"""OCR mechanics shared by document ingestion's two consumers (ADR-0018):
the chunked RAG corpus (chunking.py, primary) and term-candidate extraction
(extractors/document_ocr.py, secondary). Lives outside extractors/ because
it isn't itself an extraction source - it produces plain text, not
TermCandidates.

Deterministic, no LLM (ADR-0004's Extract stage): per page, try pypdf's
text-layer extraction first - most source PDFs have one. A page with a
near-empty text layer is a scan, so it's rendered to an image (pdf2image)
and OCR'd (pytesseract) instead.
"""

from __future__ import annotations

from pathlib import Path

import pypdf
import pypdf.errors

_MIN_TEXT_LAYER_CHARS = 20  # below this, treat the page as scanned


def find_intake_documents(intake_dir: Path) -> tuple[Path, ...]:
    """Every PDF in the intake directory, sorted for deterministic ordering."""
    if not intake_dir.is_dir():
        return ()
    return tuple(sorted(intake_dir.glob("*.pdf")))


def _page_text(page: pypdf.PageObject) -> str:
    """A page's text, via its text layer or an OCR fallback."""
    text = page.extract_text()
    if len(text.strip()) >= _MIN_TEXT_LAYER_CHARS:
        return text
    return _ocr_page(page)


def _ocr_page(page: pypdf.PageObject) -> str:  # pragma: no cover - needs tesseract
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


def extract_text_from_document(path: Path) -> str:
    """A PDF's full text, page by page, via text layer or OCR fallback.

    A corrupt or unreadable PDF yields empty text rather than raising -
    one bad file shouldn't fail extraction for the whole intake directory.
    """
    try:
        reader = pypdf.PdfReader(path)
    except pypdf.errors.PdfReadError, OSError:
        return ""
    return "\n".join(_page_text(page) for page in reader.pages)
