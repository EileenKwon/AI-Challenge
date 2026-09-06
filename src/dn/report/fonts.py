"""상담용 요약서 PDF용 한글 폰트 사전 서브셋.

WeasyPrint 는 PDF에 폰트를 임베드할 때 매 렌더링마다 서브셋(사용된 글자만
추려내는 작업)을 다시 계산한다. 시스템에 설치된 "Noto Sans CJK KR"는 실제로는
JP/KR/SC/TC/HK 5개 지역 서체를 하나의 .ttc 파일에 묶어 둔 대형 폰트라, 이
글자 중 몇 글자만 쓰더라도 서브셋 계산 자체가 전체 글자표를 훑어야 해서 매번
4~5초가 걸린다(2026-09-06 실측, `docs/report_timing.md` 참고).

실제 보고서에 필요한 글자는 현대 한글 음절(U+AC00-D7A3 — 조합 가능한 모든
현대 한글 음절을 전부 포함하는 범위라, 채권자명 등 어떤 한글 문자열이 와도
빠짐없이 커버된다) + 라틴 + 통화기호·구두점뿐이다. 이 범위만 미리 한 번
잘라낸 작은 폰트 파일을 만들어 재사용하면, 매 렌더링에서 WeasyPrint 가
다시 서브셋할 글자표 자체가 작아져 렌더링이 10배 이상 빨라진다(실측
4.5초 → 0.4~0.5초).

컨테이너가 뜬 뒤 첫 렌더링 때 한 번만 만들어 디스크에 캐시한다 — Dockerfile
빌드 단계를 건드리지 않기 위해서다. 시스템에 소스 CJK 폰트가 없는
개발환경(예: macOS 로컬 실행)에서도 그대로 동작하도록, 실패하면 예외를
삼키고 `None`을 돌려준다 — 호출부는 이 경우 기존 방식(시스템 폰트 이름
지정)으로 조용히 폴백한다.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from dn.settings import Settings

logger = logging.getLogger(__name__)

# 현대 한글 음절 전체(U+AC00-D7A3) + 자모 + 라틴/Latin-1 + 통화기호·구두점.
# 한글은 음절이 초성·중성·종성 조합으로 유한하게 정해지는 표음문자라, 이
# 범위 하나로 "가능한 모든 현대 한글 단어"를 빠짐없이 커버한다 — 특정 인명·
# 상호를 사전에 알 필요가 없다.
_SUBSET_UNICODES = "U+0000-024F,U+1100-11FF,U+20A0-20CF,U+2000-206F,U+AC00-D7A3,U+3130-318F"
_SOURCE_FONT_CANDIDATES = (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),)
_SOURCE_FACE_NAME = "Noto Sans CJK KR"
_CACHE_SUBDIR = "_fonts"
_CACHE_FILENAME = "NotoSansKR-subset.otf"

_lock = threading.Lock()
_cached_path: Path | None = None
_attempted = False


def get_subset_font_path(settings: Settings) -> Path | None:
    """서브셋 폰트 파일 경로를 반환한다. 없으면 만든다. 실패하면 `None`.

    프로세스 생애주기 동안 한 번만 시도한다(성공하든 실패하든) — 매 요청마다
    실패한 시도를 반복해 지연을 키우지 않기 위해서다.
    """
    global _cached_path, _attempted
    with _lock:
        if _cached_path is not None and _cached_path.exists():
            return _cached_path
        if _attempted:
            return None
        _attempted = True

        out_path = settings.upload_dir / _CACHE_SUBDIR / _CACHE_FILENAME
        if out_path.exists():
            _cached_path = out_path
            return out_path

        try:
            _build_subset(out_path)
        except Exception:
            logger.warning("report_font_subset_failed", exc_info=True)
            return None
        _cached_path = out_path
        return out_path


def _find_source_font() -> Path | None:
    """`fc-match` 로 실제 설치 경로를 찾는다. 배포 OS(Debian trixie)와 개발 OS가
    달라 `fonts-noto-cjk` 패키지의 설치 경로가 서로 다를 수 있다는 걸 이번
    세션에서 여러 번 겪었다 — 경로를 하드코딩하지 않고 fontconfig 에게 직접
    묻는다. `fc-match` 가 없거나 실패하면 알려진 경로 후보로 폴백한다.
    """
    import shutil
    import subprocess

    if shutil.which("fc-match"):
        try:
            result = subprocess.run(
                ["fc-match", _SOURCE_FACE_NAME, "--format", "%{file}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            path = Path(result.stdout.strip())
            if path.exists():
                return path
        except (subprocess.SubprocessError, OSError):
            pass
    return next((p for p in _SOURCE_FONT_CANDIDATES if p.exists()), None)


def _build_subset(out_path: Path) -> None:
    source = _find_source_font()
    if source is None:
        raise FileNotFoundError("소스 CJK 폰트를 찾을 수 없습니다.")

    from fontTools import subset
    from fontTools.ttLib import TTCollection

    with TTCollection(str(source)) as tc:
        font_index = next(
            i for i, f in enumerate(tc.fonts) if f["name"].getDebugName(1) == _SOURCE_FACE_NAME
        )

    options = subset.Options()
    options.font_number = font_index
    options.layout_features = ["*"]
    options.glyph_names = True
    options.symbol_cmap = True
    options.legacy_cmap = True
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]

    font = subset.load_font(str(source), options)
    unicodes = subset.parse_unicodes(_SUBSET_UNICODES)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")
    subset.save_font(font, str(tmp_path), options)
    tmp_path.replace(out_path)
