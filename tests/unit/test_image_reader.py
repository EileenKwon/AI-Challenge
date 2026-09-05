"""T03b — 이미지 인제스트(OCR) 테스트.

2026-09-06 버그 리포트: PNG 업로드가 PDF 판독기(pypdf)로 잘못 전달되어
"PDF 를 열 수 없습니다" 로 크래시하던 문제. 이미지는 반드시 이 모듈을 거쳐야
하며 pypdf 를 호출하지 않는다. 로컬 개발 환경에는 tesseract 바이너리가 없을
수 있으므로, OCR 호출 자체는 monkeypatch 로 대체하고 이 모듈의 파이프라인
(검증 → 재오픈 → 반환 스키마 → 빈 결과 처리)만 검증한다. 실제 OCR 품질은
tesseract 가 설치된 배포 환경에서 별도로 E2E 검증한다.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from dn.domain.errors import ExtractionError
from dn.ingest import image_reader


def _write_real_png(path) -> None:
    img = Image.new("RGB", (100, 40), color="white")
    img.save(path, format="PNG")


def _write_real_jpeg(path) -> None:
    img = Image.new("RGB", (100, 40), color="white")
    img.save(path, format="JPEG")


def test_read_pdf_reader_is_never_imported_for_images() -> None:
    """회귀 고정 — 이 모듈은 pypdf/PdfReader 를 임포트하지 않는다."""
    assert "pypdf" not in image_reader.__dict__
    assert not hasattr(image_reader, "PdfReader")


def test_read_returns_document_content_with_ocr_text(tmp_path, monkeypatch) -> None:
    path = tmp_path / "scan.png"
    _write_real_png(path)

    monkeypatch.setattr(
        "pytesseract.image_to_string", lambda img, lang=None: "OO캐피탈 채무 3건 46,000,000원"
    )

    doc = image_reader.read(path, doc_id="scan.png")
    assert doc.is_scanned is True
    assert len(doc.pages) == 1
    assert doc.pages[0].text == "OO캐피탈 채무 3건 46,000,000원"


def test_read_accepts_jpeg(tmp_path, monkeypatch) -> None:
    path = tmp_path / "scan.jpg"
    _write_real_jpeg(path)
    monkeypatch.setattr("pytesseract.image_to_string", lambda img, lang=None: "일부 텍스트")

    doc = image_reader.read(path, doc_id="scan.jpg")
    assert doc.pages[0].text == "일부 텍스트"


def test_read_handles_empty_ocr_result_without_crashing(tmp_path, monkeypatch) -> None:
    """글자를 하나도 인식하지 못해도 예외를 던지지 않고 빈 페이지로 남긴다."""
    path = tmp_path / "blank.png"
    _write_real_png(path)
    monkeypatch.setattr("pytesseract.image_to_string", lambda img, lang=None: "   ")

    doc = image_reader.read(path, doc_id="blank.png")
    assert doc.pages[0].text is None


def test_read_rejects_corrupted_image(tmp_path) -> None:
    """확장자는 .png 지만 실제로는 이미지가 아닌 경우 — 업로드 검증을 통과했더라도
    (예: 향후 시그니처 검사 우회) 여기서도 한 번 더 막는다."""
    path = tmp_path / "broken.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4)  # 헤더만 있고 나머지는 깨진 데이터

    with pytest.raises(ExtractionError, match="이미지 파일을 읽을 수 없습니다"):
        image_reader.read(path, doc_id="broken.png")


def test_read_error_message_differs_from_pdf_error(tmp_path) -> None:
    """PDF 오류 문구("PDF 를 열 수 없습니다")를 이미지 오류에 재사용하지 않는다."""
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image at all")

    with pytest.raises(ExtractionError) as exc_info:
        image_reader.read(path, doc_id="broken.png")
    assert "PDF" not in str(exc_info.value)
    assert "이미지" in str(exc_info.value)


def test_real_image_bytes_round_trip_via_bytesio() -> None:
    """Pillow 가 실제로 유효한 이미지를 만들고 검증할 수 있는지 sanity check."""
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    buf.seek(0)
    with Image.open(buf) as img:
        img.verify()
