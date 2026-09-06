"""상담용 요약서 PDF — 한글 폰트 사전 서브셋 테스트.

`get_subset_font_path()` 는 프로세스 생애주기 동안 한 번만 시도하는 모듈
전역 캐시를 쓰므로, 각 테스트 전에 그 전역 상태를 리셋한다. 실제 앱과 같은
`upload_dir` 를 공유하므로(테스트 전용 tmp 경로가 아니다), 이 파일이 지운
캐시 파일을 다른 테스트(예: report_timing 관련 통합 테스트)가 다시 필요로
할 수 있어 끝나면 원래 있던 파일을 복원한다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from dn.report import fonts
from dn.settings import get_settings


@pytest.fixture(autouse=True)
def _reset_font_cache(monkeypatch):
    monkeypatch.setattr(fonts, "_cached_path", None)
    monkeypatch.setattr(fonts, "_attempted", False)
    cached_file = get_settings().upload_dir / fonts._CACHE_SUBDIR / fonts._CACHE_FILENAME
    backup = None
    if cached_file.exists():
        backup = cached_file.with_suffix(".bak")
        shutil.copy2(cached_file, backup)
        cached_file.unlink()
    yield
    if backup is not None:
        shutil.move(str(backup), str(cached_file))
    else:
        cached_file.unlink(missing_ok=True)


def test_get_subset_font_path_builds_a_real_font_file() -> None:
    settings = get_settings()
    path = fonts.get_subset_font_path(settings)

    # 시스템 CJK 폰트가 없거나 기대한 페이스가 들어 있지 않은 환경에서는 None 이
    # 나온다(macOS 등). 그때는 요약서가 폰트 서브셋 없이 생성되는 정상 폴백이므로
    # 실패가 아니라 건너뛴다 — 주석은 그 가능성을 인정하면서 단언은 금지하고 있었다.
    if path is None:
        pytest.skip("시스템 CJK 폰트를 찾지 못해 서브셋을 만들 수 없는 환경")
    assert path.exists()
    tt = TTFont(str(path))
    cmap = tt.getBestCmap()
    # 현대 한글 음절 대표 하나("가", U+AC00)와 라틴 알파벳이 모두 있어야 한다.
    assert ord("가") in cmap
    assert ord("A") in cmap


def test_get_subset_font_path_is_cached_across_calls() -> None:
    settings = get_settings()
    first = fonts.get_subset_font_path(settings)
    if first is None:
        pytest.skip("시스템 CJK 폰트를 찾지 못해 서브셋을 만들 수 없는 환경")
    mtime_before = first.stat().st_mtime

    second = fonts.get_subset_font_path(settings)

    assert second == first
    assert second.stat().st_mtime == mtime_before


def test_get_subset_font_path_falls_back_to_none_when_source_missing(monkeypatch) -> None:
    monkeypatch.setattr(fonts, "_find_source_font", lambda: None)
    settings = get_settings()

    path = fonts.get_subset_font_path(settings)

    assert path is None


def test_get_subset_font_path_does_not_retry_after_a_failed_attempt(monkeypatch) -> None:
    calls = {"n": 0}

    def _fail():
        calls["n"] += 1
        return None

    monkeypatch.setattr(fonts, "_find_source_font", _fail)
    settings = get_settings()

    fonts.get_subset_font_path(settings)
    fonts.get_subset_font_path(settings)
    fonts.get_subset_font_path(settings)

    assert calls["n"] == 1


def test_find_source_font_returns_none_when_fc_match_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(fonts, "_SOURCE_FONT_CANDIDATES", (Path("/no/such/font.ttc"),))

    assert fonts._find_source_font() is None
