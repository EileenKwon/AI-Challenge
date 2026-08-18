"""T03 — 업로드 검증·안전 파일명 테스트."""

from __future__ import annotations

import pytest

from dn.ingest.uploader import UploadValidationError, safe_filename, validate_upload
from dn.settings import get_settings


def test_validate_upload_accepts_pdf_within_limit() -> None:
    settings = get_settings()
    validate_upload(
        filename="report.pdf", content_type="application/pdf", size_bytes=1024, settings=settings
    )


def test_validate_upload_rejects_oversized_file() -> None:
    settings = get_settings()
    max_bytes = settings.config.ingest.max_upload_mb * 1024 * 1024
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="report.pdf",
            content_type="application/pdf",
            size_bytes=max_bytes + 1,
            settings=settings,
        )


def test_validate_upload_rejects_disallowed_mime() -> None:
    settings = get_settings()
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="malware.exe",
            content_type="application/x-msdownload",
            size_bytes=100,
            settings=settings,
        )


def test_validate_upload_rejects_mismatched_extension() -> None:
    settings = get_settings()
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="report.exe",
            content_type="application/pdf",
            size_bytes=100,
            settings=settings,
        )


def test_validate_upload_accepts_jpeg_and_jpg_extensions() -> None:
    settings = get_settings()
    validate_upload(
        filename="scan.jpg", content_type="image/jpeg", size_bytes=100, settings=settings
    )
    validate_upload(
        filename="scan.jpeg", content_type="image/jpeg", size_bytes=100, settings=settings
    )


def test_safe_filename_strips_path_traversal() -> None:
    result = safe_filename("../../etc/passwd.pdf")
    assert "/" not in result
    assert ".." not in result
    assert result.endswith(".pdf")


def test_safe_filename_is_unique_per_call() -> None:
    a = safe_filename("report.pdf")
    b = safe_filename("report.pdf")
    assert a != b
