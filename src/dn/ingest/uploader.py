"""업로드 파일 검증과 안전한 파일명 생성.

브라우저/OS 마다 같은 파일을 서로 다른 MIME 문자열로 보고하는 사례가 실측되어
있다 — 예: 한글 오피스 뷰어가 연동된 일부 Windows 환경은 정상 PDF 를
``application/haansoftpdf`` 로 보고한다(버그 리포트, 2026-09-06). 이런 환경
차이에는 관대하되, 실제 파일 내용(확장자 + magic signature)에는 엄격해야
위장 업로드(.exe→.pdf, HTML→.pdf 등)를 계속 막을 수 있다.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from dn.domain.errors import DomainError
from dn.settings import Settings

logger = logging.getLogger(__name__)

# 브라우저/OS 가 보내는 MIME 별칭 → 프로젝트가 다루는 정규 MIME.
# `settings.config.ingest.allowed_mime` (config.yaml) 이 "어떤 형식을 허용할지"의
# 유일한 출처이고, 여기 별칭 표는 "같은 형식을 브라우저가 다르게 부르는 방법"만
# 다룬다 — 정책이 아니라 호환성 매핑이라 하드코딩해도 AGENTS.md 절대 규칙 9 위반이
# 아니다.
_MIME_ALIASES: dict[str, str] = {
    "application/pdf": "application/pdf",
    "application/x-pdf": "application/pdf",
    "application/haansoftpdf": "application/pdf",  # 한컴 연동 Windows 환경 실측
    "application/acrobat": "application/pdf",
    "application/vnd.pdf": "application/pdf",
    "image/png": "image/png",
    "image/x-png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
}

# MIME 을 신뢰하지 않고 파일 내용의 magic signature 로 직접 판별할 값들.
_SNIFFABLE_MIME = {"", "application/octet-stream"}

_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}

_ALLOWED_EXTENSIONS: dict[str, frozenset[str]] = {
    "application/pdf": frozenset({".pdf"}),
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
}

_FORMAT_LABELS: dict[str, str] = {
    "application/pdf": "PDF",
    "image/png": "PNG",
    "image/jpeg": "JPG/JPEG",
}

# 정규 MIME → 처리기 종류. PDF 와 이미지는 완전히 다른 판독기(pypdf vs. OCR)를
# 타야 하므로, 검증에서 이미 확정한 정규 MIME 을 그대로 재사용해 라우터가
# 다시 판별하지 않게 한다 — 판별 로직이 두 곳에 흩어지면 한쪽만 고치고
# 잊는 회귀(이번 haansoftpdf/PNG 버그가 그 사례)가 반복된다.
_FILE_KINDS: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "image",
    "image/jpeg": "image",
}

_REJECTION_MESSAGE = "지원하지 않는 파일 형식입니다. {formats} 파일을 사용해 주세요."


class UploadValidationError(DomainError):
    """업로드 파일이 크기·MIME·확장자·내용 제약을 위반했다."""


def supported_format_label(settings: Settings) -> str:
    """업로드 화면 안내와 오류 메시지가 같은 허용 목록을 보게 하는 단일 출처."""
    return ", ".join(
        _FORMAT_LABELS[mime]
        for mime in settings.config.ingest.allowed_mime
        if mime in _FORMAT_LABELS
    )


def _canonical_mime(content_type: str, *, content_head: bytes) -> str | None:
    """브라우저가 보낸 MIME 을 정규 MIME 으로 정규화한다.

    별칭 표에 있으면 그대로 정규화한다. 비어 있거나 `application/octet-stream`
    처럼 브라우저가 실제 타입을 알려주지 않을 때만 파일 내용의 magic signature 로
    직접 판별한다 — 이때도 signature 가 실제로 일치해야 통과하므로 검증 수준은
    낮아지지 않는다. 그 밖의 알 수 없는 MIME(예: `text/html`, `.hwpx` 류)은
    안전하게 거부한다.
    """
    mime = (content_type or "").lower().strip()
    if mime in _MIME_ALIASES:
        return _MIME_ALIASES[mime]
    if mime in _SNIFFABLE_MIME:
        for candidate, signatures in _SIGNATURES.items():
            if any(content_head.startswith(sig) for sig in signatures):
                return candidate
        return None
    return None


def file_kind_for(canonical_mime: str) -> str:
    """정규 MIME 에서 처리기 종류("pdf"/"image")를 얻는다."""
    return _FILE_KINDS[canonical_mime]


def validate_upload(
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    content: bytes,
    settings: Settings,
) -> str:
    """크기·MIME(별칭 포함)·확장자·magic signature 정합성을 검증한다.

    위반 시 `UploadValidationError` 를 던진다. 사용자에게는 일반적인 안내 문구만
    보여주고, 실제 클라이언트 MIME·판별 결과는 로그에만 남긴다(문서 내용은 남기지
    않는다). 통과하면 정규 MIME 을 반환한다 — 호출자가 이 값으로 `file_kind_for()`
    를 호출해 PDF/이미지 처리기를 정확히 나눠 타게 한다.
    """
    max_bytes = settings.config.ingest.max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise UploadValidationError(
            f"파일 크기가 허용치를 초과했습니다: {size_bytes} > {max_bytes} bytes"
        )

    ext = Path(filename).suffix.lower()
    formats = supported_format_label(settings)
    canonical_mime = _canonical_mime(content_type, content_head=content[:16])

    if canonical_mime is None or canonical_mime not in settings.config.ingest.allowed_mime:
        logger.warning(
            "rejected_upload: unsupported mime — filename_ext=%s client_mime=%s",
            ext,
            content_type,
        )
        raise UploadValidationError(_REJECTION_MESSAGE.format(formats=formats))

    allowed_ext = _ALLOWED_EXTENSIONS.get(canonical_mime, frozenset())
    if ext not in allowed_ext:
        logger.warning(
            "rejected_upload: extension mismatch — filename_ext=%s client_mime=%s detected_type=%s",
            ext,
            content_type,
            canonical_mime,
        )
        raise UploadValidationError(_REJECTION_MESSAGE.format(formats=formats))

    signatures = _SIGNATURES.get(canonical_mime, ())
    if signatures and not any(content.startswith(sig) for sig in signatures):
        logger.warning(
            "rejected_upload: signature mismatch — filename_ext=%s client_mime=%s detected_type=%s",
            ext,
            content_type,
            canonical_mime,
        )
        raise UploadValidationError(_REJECTION_MESSAGE.format(formats=formats))

    return canonical_mime


def safe_filename(original_filename: str) -> str:
    """경로 조작 문자를 제거하고 충돌을 막기 위해 uuid 기반 파일명을 생성한다."""
    ext = Path(original_filename).suffix.lower()
    ext = re.sub(r"[^a-z0-9.]", "", ext)
    return f"{uuid.uuid4().hex}{ext}"
