"""T03 — PDF 인제스트 테스트.

2026-09-06 갭 수정: `_render_page_image()` 가 만든 스캔 페이지 이미지가 OCR 로
연결되지 않아 스캔 PDF 가 항상 채무 0건으로 나오던 문제. 이 파일의 로컬
개발 환경에는 tesseract 바이너리가 없으므로, 실제 OCR 호출은 monkeypatch 로
대체하고 분기(텍스트 페이지는 OCR 을 타지 않는지 / 스캔 페이지는 렌더링된
이미지에 OCR 을 돌리는지)만 검증한다. 실제 OCR 품질은 Render 배포 환경에서
별도로 E2E 검증한다.
"""

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


def test_text_pdf_never_calls_ocr(monkeypatch) -> None:
    """정상 text PDF 는 텍스트 레이어만으로 충분하므로 OCR 을 아예 호출하지 않는다."""
    called = False

    def _spy(img, lang=None):
        nonlocal called
        called = True
        return ""

    monkeypatch.setattr("pytesseract.image_to_string", _spy)
    pdf_reader.read(_FIXTURES / "sample_text.pdf", doc_id="doc-text-spy")
    assert called is False


def test_scanned_pdf_is_flagged_and_rendered(monkeypatch) -> None:
    # 이 fixture 는 실제 글자가 없는 빈 이미지다 — OCR 을 실제로 돌려도(배포 환경)
    # 빈 결과가 나오는 게 맞지만, 로컬에는 tesseract 바이너리가 없으므로 그
    # "빈 결과" 자체를 흉내내 렌더링/플래그 동작만 검증한다.
    monkeypatch.setattr("pytesseract.image_to_string", lambda img, lang=None: "")
    doc = pdf_reader.read(_FIXTURES / "sample_scanned.pdf", doc_id="doc-scanned")
    assert doc.is_scanned is True
    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert page.text is None
    # poppler(pdftoppm)와 pdf2image 가 설치된 환경이므로 렌더링된 이미지가 남아야 한다.
    assert page.image_path is not None
    assert Path(page.image_path).exists()


def test_scanned_pdf_ocr_result_becomes_page_text(monkeypatch) -> None:
    """렌더링된 스캔 페이지 이미지가 실제로 OCR 을 거쳐 page.text 에 반영된다."""
    monkeypatch.setattr(
        "pytesseract.image_to_string", lambda img, lang=None: "OO캐피탈 채무 3건 46,000,000원"
    )
    doc = pdf_reader.read(_FIXTURES / "sample_scanned.pdf", doc_id="doc-scanned-ocr")
    assert doc.is_scanned is True
    page = doc.pages[0]
    assert page.text == "OO캐피탈 채무 3건 46,000,000원"
    assert page.image_path is not None


def test_scanned_pdf_ocr_uses_same_language_setting_as_image_upload(monkeypatch) -> None:
    """PDF 스캔 페이지와 PNG/JPEG 업로드가 동일한 언어 설정(kor+eng)으로 OCR 을 호출한다."""
    seen_langs = []

    def _spy(img, lang=None):
        seen_langs.append(lang)
        return "인식된 한글 텍스트"

    monkeypatch.setattr("pytesseract.image_to_string", _spy)
    pdf_reader.read(_FIXTURES / "sample_scanned.pdf", doc_id="doc-scanned-lang")
    assert seen_langs == ["kor+eng"]


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


def test_corrupted_pdf_error_message_has_no_internal_path(tmp_path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nnot a real pdf body, deliberately corrupt")

    with pytest.raises(ExtractionError) as exc_info:
        pdf_reader.read(path, doc_id="doc-broken")
    msg = str(exc_info.value)
    assert str(path) not in msg
    assert "PDF 파일을 읽을 수 없습니다" in msg


def test_scanned_pdf_ocr_engine_missing_raises_extraction_error_without_leaking_path(
    monkeypatch,
) -> None:
    """tesseract 바이너리 자체가 없을 때도(배포 오설정 등) 크래시 대신 안내 메시지로 떨어진다."""
    import pytesseract

    def _raise(img, lang=None):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr("pytesseract.image_to_string", _raise)
    with pytest.raises(ExtractionError) as exc_info:
        pdf_reader.read(_FIXTURES / "sample_scanned.pdf", doc_id="doc-scanned-noengine")
    msg = str(exc_info.value)
    assert "/" not in msg
    assert "인식하지 못했습니다" in msg
