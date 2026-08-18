"""PDF 인제스트 — 텍스트 레이어 유무로 분기해 `DocumentContent` 를 만든다.

페이지당 추출 문자 수가 임계치(`config: ingest.min_text_chars`) 미만이면
해당 페이지를 스캔본으로 간주하고 렌더링 이미지로 대체한다.
"""

from __future__ import annotations

from pathlib import Path

import pypdf

from dn.domain.errors import ExtractionError
from dn.domain.models import DocumentContent, PageContent
from dn.settings import Settings, get_settings


def read(path: Path, *, doc_id: str, settings: Settings | None = None) -> DocumentContent:
    """PDF 를 읽어 `DocumentContent` 로 변환한다. 암호화된 PDF 는 명시적으로 거부한다."""
    settings = settings or get_settings()
    threshold = settings.config.ingest.min_text_chars

    try:
        reader = pypdf.PdfReader(str(path))
    except Exception as exc:
        raise ExtractionError(f"PDF 를 열 수 없습니다: {path.name} ({exc})") from exc

    if reader.is_encrypted:
        raise ExtractionError(f"암호화된 PDF 는 지원하지 않습니다: {path.name}")

    pages: list[PageContent] = []
    any_scanned = False
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if len(text) >= threshold:
            pages.append(PageContent(page_no=i, text=text, image_path=None))
            continue
        any_scanned = True
        image_path = _render_page_image(path, i, settings=settings)
        pages.append(PageContent(page_no=i, text=None, image_path=image_path))

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
