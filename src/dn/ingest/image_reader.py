"""이미지 인제스트 — Pillow 로 실제 이미지인지 검증하고 OCR 로 텍스트를 뽑는다.

신용정보조회서를 사진/캡처로 보유한 사용자를 위한 경로다. `pdf_reader.read()`
(pypdf)를 이미지에 호출하면 즉시 크래시한다 — PDF 와 이미지는 완전히 다른
판독기를 타야 한다(2026-09-06 버그 리포트: PNG 업로드 시 "PDF 를 열 수
없습니다" 크래시). 이미지는 텍스트 레이어가 없으므로 OCR(tesseract,
한국어+영어)로 문서 텍스트를 만들어, 이후 파이프라인(인젝션 스캔 → PII 마스킹
→ LLM 추출)에 PDF 네이티브 텍스트와 동일한 `DocumentContent` 스키마로 태운다 —
03 화면 이후는 입력 방식을 구분하지 않는다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from dn.domain.errors import ExtractionError
from dn.domain.models import DocumentContent, PageContent

logger = logging.getLogger(__name__)


def ocr_text_from_image(image_path: Path) -> str | None:
    """이미지 파일을 열어 OCR로 텍스트를 뽑는다. 글자를 인식하지 못하면 `None`.

    업로드된 PNG/JPEG(이 모듈)와 `pdf_reader`가 렌더링한 스캔 PDF 페이지
    이미지가 동일한 이 함수를 거치게 한다 — Tesseract 호출을 두 곳에
    따로 두면 한쪽만 언어팩·파라미터를 바꾸는 회귀가 생기기 때문이다.
    호출 전에 `pytesseract` 가 설치돼 있는지는 호출부에서 확인한다.
    """
    import pytesseract

    with Image.open(image_path) as img:
        text = pytesseract.image_to_string(img, lang="kor+eng").strip()
    return text or None


def read(path: Path, *, doc_id: str) -> DocumentContent:
    """이미지를 읽어 OCR 텍스트가 담긴 `DocumentContent` 로 변환한다.

    OCR 로 글자를 하나도 인식하지 못해도(빈 이미지 등) 예외를 던지지 않고
    빈 페이지로 남긴다 — 스캔 PDF에서 렌더링에 실패한 페이지를 빈 페이지로
    두는 기존 `pdf_reader` 동작과 같다. 이 경우 추출 단계가 채무 0건을
    반환하고, 사용자는 화면 02의 "문서 없이 직접 입력"으로 넘어갈 수 있다.

    사용자에게 보이는 메시지에는 원본 예외 텍스트나 서버 내부 경로를 절대
    포함하지 않는다 — Pillow 의 `UnidentifiedImageError` 는 종종 전체 파일
    경로(`/app/var/uploads/...`)를 그대로 메시지에 담고 있어, 그대로
    노출하면 서버 내부 구조가 클라이언트에 새어 나간다. 진단에 필요한
    상세는 문서 내용 없이 파일명·예외 클래스만 서버 로그에 남긴다.
    """
    try:
        with Image.open(path) as img:
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning(
            "image_open_failed",
            extra={"upload_filename": path.name, "exception_class": type(exc).__name__},
        )
        raise ExtractionError(
            "이미지 파일을 읽을 수 없습니다. PNG 또는 JPG/JPEG 파일인지 확인해 주세요."
        ) from exc

    try:
        import pytesseract
    except ImportError as exc:
        raise ExtractionError("이미지 텍스트 인식 기능을 사용할 수 없습니다.") from exc

    try:
        # img.verify() 는 검증 후 파일 핸들을 못 쓰게 만들므로 ocr_text_from_image 가 다시 연다.
        text = ocr_text_from_image(path)
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as exc:
        logger.warning(
            "image_ocr_failed",
            extra={"upload_filename": path.name, "exception_class": type(exc).__name__},
        )
        raise ExtractionError(
            "이미지에서 글자를 인식하지 못했습니다. 더 선명한 사진으로 다시 시도해 주세요."
        ) from exc

    return DocumentContent(
        doc_id=doc_id,
        filename=path.name,
        is_scanned=True,
        pages=(PageContent(page_no=1, text=text, image_path=str(path)),),
    )
