"""전역 테스트 픽스처.

`get_session_store()`/`get_settings()` 는 `lru_cache` 싱글턴이라, 아무 조치 없이
두면 테스트가 프로젝트 루트의 실제 `sessions.db` 를 공유하고 프로세스 전체에서
캐시된 인스턴스를 재사용한다 — 테스트 간 상태가 새고, 반복 실행 시 DB 파일이
계속 쌓인다. 매 테스트마다 임시 경로로 격리하고 캐시를 비운다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dn.api import ratelimit
from dn.api.deps import get_session_store
from dn.settings import get_settings


@pytest.fixture(autouse=True)
def _isolated_session_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DN_SESSION_DB", str(tmp_path / "sessions.db"))
    get_settings.cache_clear()
    get_session_store.cache_clear()
    # IP 단위 호출 카운터도 비운다. 프로세스 전역이라 비우지 않으면 앞선 테스트가
    # 쓴 횟수가 쌓여서, 테스트를 추가할수록 뒤쪽 테스트가 429 로 깨진다.
    ratelimit.reset()
    yield
    ratelimit.reset()
    get_session_store.cache_clear()
    get_settings.cache_clear()
