"""PDF 인제스트 — 텍스트 레이어 유무로 분기해 `DocumentContent` 를 만든다.

페이지당 추출 문자 수가 임계치(`config: ingest.min_text_chars`, 기본 50자)
미만이면 해당 페이지를 스캔본으로 간주해 렌더링 이미지로 대체하고,
PNG/JPEG 업로드와 동일한 Tesseract OCR(`image_reader.ocr_text_from_image`)로
텍스트를 뽑아 이후 LLM 추출 파이프라인에 그대로 태운다(2026-09-06 갭:
렌더링만 하고 OCR 로 연결하지 않아 스캔 PDF 가 채무 0건으로 나오던 문제).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pypdf

from dn.domain.errors import ExtractionError
from dn.domain.models import DocumentContent, PageContent
from dn.ingest.image_reader import ocr_text_from_image
from dn.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def read(path: Path, *, doc_id: str, settings: Settings | None = None) -> DocumentContent:
    """PDF 를 읽어 `DocumentContent` 로 변환한다. 암호화된 PDF 는 명시적으로 거부한다.

    사용자에게 보이는 메시지에는 원본 예외 텍스트나 서버 내부 경로를 절대
    포함하지 않는다 — pypdf/PIL 의 예외 메시지가 종종 전체 파일 경로를
    그대로 담고 있어 그대로 노출하면 정보 노출이 된다. 진단에 필요한
    상세는 문서 내용 없이 파일명·예외 클래스만 서버 로그에 남긴다.
    """
    settings = settings or get_settings()
    threshold = settings.config.ingest.min_text_chars

    try:
        reader = pypdf.PdfReader(str(path))
    except Exception as exc:
        logger.warning(
            "pdf_open_failed",
            extra={"upload_filename": path.name, "exception_class": type(exc).__name__},
        )
        raise ExtractionError(
            "PDF 파일을 읽을 수 없습니다. 손상되지 않은 PDF인지 확인해 주세요."
        ) from exc

    if reader.is_encrypted:
        raise ExtractionError(
            "암호화된 PDF 는 지원하지 않습니다. 암호를 해제한 뒤 다시 업로드해 주세요."
        )

    pages: list[PageContent] = []
    any_scanned = False
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if len(text) >= threshold:
            pages.append(PageContent(page_no=i, text=text, image_path=None))
            continue
        any_scanned = True
        image_path = _render_page_image(path, i, settings=settings)
        page_text = _ocr_rendered_page(image_path)
        pages.append(PageContent(page_no=i, text=page_text, image_path=image_path))

    return DocumentContent(
        doc_id=doc_id,
        filename=path.name,
        is_scanned=any_scanned,
        pages=tuple(pages),
    )


def _render_page_image(path: Path, page_no: int, *, settings: Settings) -> str | None:
    """스캔본 페이지를 PNG 로 렌더링한다. `pdf2image`/poppler 가 없으면 `None` 을 반환한다."""
    try:
        from pdf2image import convert_from_path
        from pdf2image.exceptions import PDFInfoNotInstalledError
    except ImportError:
        return None

    try:
        images = convert_from_path(str(path), first_page=page_no, last_page=page_no)
    except PDFInfoNotInstalledError:
        return None
    if not images:
        return None

    out_dir = settings.upload_dir / "_rendered" / path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"page_{page_no}.png"
    images[0].save(out_path)
    return str(out_path)


def _ocr_rendered_page(image_path: str | None) -> str | None:
    """렌더링된 스캔 페이지 이미지에 OCR 을 돌린다. 렌더링 자체가 안 됐으면(poppler
    미설치 등) `None` 을 그대로 돌려준다 — 기존 폴백(빈 페이지)을 유지한다.

    OCR 실패는 문서 전체를 못 읽는 것과 같은 무게의 오류로 본다 — 이미지
    업로드 경로(`image_reader.read`)와 동일한 판단이다. 원본 예외 텍스트나
    서버 내부 경로는 사용자에게 보이는 메시지에 포함하지 않는다.
    """
    if image_path is None:
        return None

    try:
        import pytesseract
    except ImportError as exc:
        raise ExtractionError("이미지 텍스트 인식 기능을 사용할 수 없습니다.") from exc

    try:
        return ocr_text_from_image(Path(image_path))
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as exc:
        logger.warning("pdf_page_ocr_failed", extra={"exception_class": type(exc).__name__})
        raise ExtractionError(
            "PDF 안의 이미지에서 글자를 인식하지 못했습니다. "
            "더 선명한 스캔본으로 다시 시도해 주세요."
        ) from exc
