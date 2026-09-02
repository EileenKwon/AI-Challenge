"""IP 단위 호출 빈도 제한.

LLM 을 호출하는 두 엔드포인트(문서 업로드·분석)만 막는다. 이 서비스는 공개
URL 로 배포되고 뒤에 과금되는(또는 무료 티어 한도가 있는) LLM 백엔드가 붙으므로,
제한이 없으면 스크립트 한 번에 한도가 소진되거나 요금이 발생한다.

ponytail: 단일 프로세스 메모리 카운터다. 워커를 여러 개로 늘리면 워커마다 따로
세므로 실효 한도가 워커 수만큼 커진다 — 그때는 Redis 같은 공유 저장소로 옮긴다.
현재 배포는 uvicorn 단일 워커라 이걸로 충분하다.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_HITS: dict[str, deque[float]] = defaultdict(deque)


def client_key(request: Request) -> str:
    """호출자 식별자. 리버스 프록시 뒤에서는 X-Forwarded-For 의 첫 IP 를 쓴다."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(key: str, *, limit: int, window_sec: int) -> None:
    """`window_sec` 안에 `limit` 회를 넘으면 429 를 던진다."""
    now = time.monotonic()
    hits = _HITS[key]
    while hits and now - hits[0] > window_sec:
        hits.popleft()
    if len(hits) >= limit:
        retry_after = int(window_sec - (now - hits[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=(
                f"요청이 너무 많습니다. {retry_after}초 후에 다시 시도해 주세요. "
                "문서 없이 직접 입력은 제한 없이 이용할 수 있습니다."
            ),
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)


def reset() -> None:
    """테스트 격리용."""
    _HITS.clear()
