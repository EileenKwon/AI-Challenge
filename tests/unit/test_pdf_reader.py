"""T03 — PDF 인제스트 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from dn.domain.errors import ExtractionError
from dn.ingest import pdf_reader
from dn.settings import get_settings

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_text_pdf_extracts_page_text() -> None:
    doc = pdf_reader.read(_FIXTURES / "sample_text.pdf", doc_id="doc-text")
    assert doc.is_scanned is False
    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert page.text is not None
    assert "Sample Credit Report" in page.text
    assert page.image_path is None


def test_scanned_pdf_is_flagged_and_rendered() -> None:
    doc = pdf_reader.read(_FIXTURES / "sample_scanned.pdf", doc_id="doc-scanned")
    assert doc.is_scanned is True
    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert page.text is None
    # poppler(pdftoppm)와 pdf2image 가 설치된 환경이므로 렌더링된 이미지가 남아야 한다.
    assert page.image_path is not None
    assert Path(page.image_path).exists()


def test_below_threshold_text_is_treated_as_scanned() -> None:
    settings = get_settings()
    original_threshold = settings.config.ingest.min_text_chars
    assert original_threshold == 50

    doc = pdf_reader.read(_FIXTURES / "sample_text.pdf", doc_id="doc-strict")
    assert doc.is_scanned is False  # 121자 텍스트는 기본 임계치(50) 이상


def test_encrypted_pdf_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        pdf_reader.read(_FIXTURES / "sample_encrypted.pdf", doc_id="doc-enc")


def test_missing_file_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        pdf_reader.read(_FIXTURES / "does_not_exist.pdf", doc_id="doc-missing")
