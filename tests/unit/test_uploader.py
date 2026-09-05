"""T03 — 업로드 검증·안전 파일명 테스트.

2026-09-06 버그 리포트: 정상 PDF 가 일부 Windows/한컴 연동 환경에서
`application/haansoftpdf` MIME 으로 전달되어 거부되는 문제를 고정한다.
MIME 은 별칭을 허용하되(호환성), 확장자·magic signature 는 계속 엄격하게
검증해(보안) 위장 업로드를 막는다.
"""

from __future__ import annotations

import pytest

from dn.ingest.uploader import UploadValidationError, safe_filename, validate_upload
from dn.settings import get_settings

_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\n%%EOF"
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32
_EXE_BYTES = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff"
_HTML_BYTES = b"<!DOCTYPE html><html><body>fake pdf</body></html>"


# --- 정상 허용 -----------------------------------------------------------------


def test_validate_upload_accepts_pdf_within_limit() -> None:
    settings = get_settings()
    validate_upload(
        filename="report.pdf",
        content_type="application/pdf",
        size_bytes=len(_PDF_BYTES),
        content=_PDF_BYTES,
        settings=settings,
    )


def test_validate_upload_accepts_haansoftpdf_mime_alias() -> None:
    """이번 버그의 핵심 재현 — 정상 PDF 인데 MIME 이 한컴 연동 환경 값으로 온 경우."""
    settings = get_settings()
    validate_upload(
        filename="report.pdf",
        content_type="application/haansoftpdf",
        size_bytes=len(_PDF_BYTES),
        content=_PDF_BYTES,
        settings=settings,
    )


def test_validate_upload_accepts_x_pdf_mime_alias() -> None:
    settings = get_settings()
    validate_upload(
        filename="report.pdf",
        content_type="application/x-pdf",
        size_bytes=len(_PDF_BYTES),
        content=_PDF_BYTES,
        settings=settings,
    )


def test_validate_upload_accepts_pdf_with_generic_octet_stream_mime() -> None:
    """브라우저가 실제 타입을 안 알려줄 때 magic signature 로 판별해 통과시킨다."""
    settings = get_settings()
    validate_upload(
        filename="report.pdf",
        content_type="application/octet-stream",
        size_bytes=len(_PDF_BYTES),
        content=_PDF_BYTES,
        settings=settings,
    )


def test_validate_upload_accepts_pdf_with_empty_mime() -> None:
    settings = get_settings()
    validate_upload(
        filename="report.pdf",
        content_type="",
        size_bytes=len(_PDF_BYTES),
        content=_PDF_BYTES,
        settings=settings,
    )


def test_validate_upload_accepts_png() -> None:
    settings = get_settings()
    validate_upload(
        filename="scan.png",
        content_type="image/png",
        size_bytes=len(_PNG_BYTES),
        content=_PNG_BYTES,
        settings=settings,
    )


def test_validate_upload_accepts_jpeg_and_jpg_extensions() -> None:
    settings = get_settings()
    validate_upload(
        filename="scan.jpg",
        content_type="image/jpeg",
        size_bytes=len(_JPEG_BYTES),
        content=_JPEG_BYTES,
        settings=settings,
    )
    validate_upload(
        filename="scan.jpeg",
        content_type="image/jpeg",
        size_bytes=len(_JPEG_BYTES),
        content=_JPEG_BYTES,
        settings=settings,
    )


# --- 반드시 거부 -----------------------------------------------------------------


def test_validate_upload_rejects_oversized_file() -> None:
    settings = get_settings()
    max_bytes = settings.config.ingest.max_upload_mb * 1024 * 1024
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="report.pdf",
            content_type="application/pdf",
            size_bytes=max_bytes + 1,
            content=_PDF_BYTES,
            settings=settings,
        )


def test_validate_upload_rejects_disallowed_mime() -> None:
    settings = get_settings()
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="malware.exe",
            content_type="application/x-msdownload",
            size_bytes=len(_EXE_BYTES),
            content=_EXE_BYTES,
            settings=settings,
        )


def test_validate_upload_rejects_extension_only_disguise() -> None:
    """확장자만 .pdf — 실제 내용은 EXE, MIME 도 정상 PDF 로 위장."""
    settings = get_settings()
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="malware.pdf",
            content_type="application/pdf",
            size_bytes=len(_EXE_BYTES),
            content=_EXE_BYTES,
            settings=settings,
        )


def test_validate_upload_rejects_mime_only_disguise() -> None:
    """MIME 만 PDF — 확장자는 .exe."""
    settings = get_settings()
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="malware.exe",
            content_type="application/pdf",
            size_bytes=len(_PDF_BYTES),
            content=_PDF_BYTES,
            settings=settings,
        )


def test_validate_upload_rejects_html_disguised_as_pdf_via_alias_mime() -> None:
    """별칭 MIME(application/haansoftpdf)이어도 실제 내용이 PDF 가 아니면 거부한다."""
    settings = get_settings()
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="fake.pdf",
            content_type="application/haansoftpdf",
            size_bytes=len(_HTML_BYTES),
            content=_HTML_BYTES,
            settings=settings,
        )


def test_validate_upload_rejects_zip_disguised_as_pdf() -> None:
    settings = get_settings()
    zip_bytes = b"PK\x03\x04" + b"\x00" * 32
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="archive.pdf",
            content_type="application/pdf",
            size_bytes=len(zip_bytes),
            content=zip_bytes,
            settings=settings,
        )


def test_validate_upload_rejects_hwpx_extension() -> None:
    """HWPX 자체 업로드는 지원하지 않는다 — PDF/이미지로 혼동해 허용하면 안 된다."""
    settings = get_settings()
    hwpx_bytes = b"PK\x03\x04" + b"\x00" * 32  # HWPX 도 ZIP 컨테이너다
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="document.hwpx",
            content_type="application/octet-stream",
            size_bytes=len(hwpx_bytes),
            content=hwpx_bytes,
            settings=settings,
        )


def test_validate_upload_rejects_unmapped_mime_even_with_valid_pdf_signature() -> None:
    """모르는 MIME 은 시그니처가 맞아도 신뢰하지 않는다 — 별칭 표에 없으면 거부."""
    settings = get_settings()
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="report.pdf",
            content_type="application/x-mystery-vendor-pdf",
            size_bytes=len(_PDF_BYTES),
            content=_PDF_BYTES,
            settings=settings,
        )


def test_validate_upload_error_message_is_generic_and_lists_supported_formats() -> None:
    settings = get_settings()
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            filename="document.hwpx",
            content_type="application/octet-stream",
            size_bytes=10,
            content=b"PK\x03\x04",
            settings=settings,
        )
    message = str(exc_info.value)
    assert "PDF" in message
    assert "application/octet-stream" not in message  # 클라이언트 MIME 원문은 로그에만


def test_safe_filename_strips_path_traversal() -> None:
    result = safe_filename("../../etc/passwd.pdf")
    assert "/" not in result
    assert ".." not in result
    assert result.endswith(".pdf")


def test_safe_filename_is_unique_per_call() -> None:
    a = safe_filename("report.pdf")
    b = safe_filename("report.pdf")
    assert a != b


def test_supported_format_label_matches_configured_allowed_mime() -> None:
    """UI 안내와 오류 메시지가 쓰는 라벨이 실제 허용 MIME 목록에서 도출됐는지 고정한다."""
    from dn.ingest.uploader import supported_format_label

    settings = get_settings()
    label = supported_format_label(settings)
    assert "PDF" in label
    assert "PNG" in label
    assert "JPG/JPEG" in label
