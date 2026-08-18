"""업로드 파일 검증과 안전한 파일명 생성."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from dn.domain.errors import DomainError
from dn.settings import Settings

_ALLOWED_EXTENSIONS: dict[str, frozenset[str]] = {
    "application/pdf": frozenset({".pdf"}),
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
}


class UploadValidationError(DomainError):
    """업로드 파일이 크기·MIME·확장자 제약을 위반했다."""


def validate_upload(
    *, filename: str, content_type: str, size_bytes: int, settings: Settings
) -> None:
    """크기·MIME·확장자 정합성을 검증한다. 위반 시 `UploadValidationError` 를 던진다."""
    max_bytes = settings.config.ingest.max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise UploadValidationError(
            f"파일 크기가 허용치를 초과했습니다: {size_bytes} > {max_bytes} bytes"
        )

    if content_type not in settings.config.ingest.allowed_mime:
        raise UploadValidationError(f"허용되지 않은 파일 형식입니다: {content_type}")

    allowed_ext = _ALLOWED_EXTENSIONS.get(content_type)
    ext = Path(filename).suffix.lower()
    if allowed_ext is None or ext not in allowed_ext:
        raise UploadValidationError(
            f"확장자가 MIME 타입과 일치하지 않습니다: {filename} ({content_type})"
        )


def safe_filename(original_filename: str) -> str:
    """경로 조작 문자를 제거하고 충돌을 막기 위해 uuid 기반 파일명을 생성한다."""
    ext = Path(original_filename).suffix.lower()
    ext = re.sub(r"[^a-z0-9.]", "", ext)
    return f"{uuid.uuid4().hex}{ext}"
