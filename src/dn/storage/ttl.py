"""만료 세션과 업로드 원본 파일 삭제 (TTL, 백그라운드 태스크).

업로드 원본은 세션별로 `upload_dir/{session_id}/` 아래 저장된다는 규약을 따른다
(T03 인제스트가 이 규약으로 파일을 쓴다). 세션이 만료되면 이 디렉토리를
통째로 삭제하고 저장소에서 세션 레코드도 지운다.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

from dn.storage.session_store import SessionStore

logger = logging.getLogger(__name__)


def session_upload_dir(upload_dir: Path, session_id: str) -> Path:
    return upload_dir / session_id


def sweep_expired_sessions(
    store: SessionStore,
    *,
    now: datetime,
    ttl_minutes: int,
    upload_dir: Path,
) -> list[str]:
    """만료된 세션의 업로드 원본과 세션 레코드를 삭제하고, 삭제된 session_id 목록을 반환한다."""
    expired = store.list_expired(now=now, ttl_minutes=ttl_minutes)
    deleted_ids: list[str] = []
    for state in expired:
        target_dir = session_upload_dir(upload_dir, state.session_id)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        store.delete(state.session_id)
        deleted_ids.append(state.session_id)
        logger.info("session_expired_and_purged", extra={"session_id": state.session_id})
    return deleted_ids


async def run_ttl_sweeper(
    store: SessionStore,
    *,
    ttl_minutes: int,
    upload_dir: Path,
    interval_seconds: int = 60,
) -> None:
    """주기적으로 `sweep_expired_sessions` 를 실행하는 백그라운드 루프.

    앱 시작 시 `asyncio.create_task(run_ttl_sweeper(...))` 형태로 구동한다 (T18에서 배선).
    """
    while True:
        sweep_expired_sessions(
            store,
            now=datetime.now(),
            ttl_minutes=ttl_minutes,
            upload_dir=upload_dir,
        )
        await asyncio.sleep(interval_seconds)
