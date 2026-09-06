"""문서 업로드 → 추출 — 비동기 작업(job) 관리.

`POST /document` 는 추출 결과를 직접 돌려주지 않는다. AI 구조화 추출(LLM 호출)
은 무료 티어 rate limit 재시도 때문에 수 초~수십 초까지 걸릴 수 있어(실측,
2026-09-06: 동일 문서로 4회 반복 시 3~14초), 요청을 즉시 202 로 받아넘기고
실제 작업은 백그라운드 스레드에서 진행한다 — `report/jobs.py` 와 같은 이유,
같은 구조다.

파일 검증(`validate_upload`)과 저장은 이 모듈에 들어오기 전에 라우터가 동기로
끝낸다 — 형식이 잘못된 파일은 기다리게 하지 않고 즉시 400 으로 알려줘야 하기
때문이다. 이 모듈이 다루는 건 "느리고 실패할 수 있는" 나머지(문서 읽기 ·
PII 마스킹 · AI 추출)뿐이다.

작업은 프로세스 메모리에만 존재한다(재시작하면 사라진다) — report job 과 같은
설계: 실패하면 사용자가 다시 업로드하면 된다.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dn.domain.enums import SessionStage
from dn.domain.errors import DomainError
from dn.domain.models import ExtractionResult
from dn.extraction.extractor import extract
from dn.ingest import image_reader, pdf_reader
from dn.ingest.injection_scanner import apply as apply_scan
from dn.ingest.injection_scanner import scan as scan_injection
from dn.ingest.pii_masker import mask as mask_pii
from dn.ingest.uploader import file_kind_for
from dn.llm.client import LLMClient
from dn.pipeline.stages import transition
from dn.settings import Settings
from dn.storage.session_store import SessionStore

logger = logging.getLogger(__name__)

STEP_NAMES = ("reading_document", "checking_content", "extracting_debts", "ready")
TOTAL_STEPS = len(STEP_NAMES)  # 1 문서 읽기 · 2 내용 확인 · 3 AI 추출 · 4 완료
FAILED = "failed"

_EXTRACTION_FAILURE_MESSAGE = (
    'AI 문서 추출을 일시적으로 사용할 수 없습니다. 아래 "직접 입력하기"로 진행해 주세요.'
)


@dataclass
class UploadJob:
    job_id: str
    session_id: str
    status: str = "reading_document"
    step: int = 1
    debt_count: int | None = None
    session_stage: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.perf_counter)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def to_status_dict(self) -> dict[str, Any]:
        with self.lock:
            if self.status == FAILED:
                return {"state": FAILED, "error": self.error}
            if self.status == "ready":
                return {
                    "state": "ready",
                    "step": TOTAL_STEPS,
                    "total_steps": TOTAL_STEPS,
                    "progress": 100,
                    "debt_count": self.debt_count,
                    "session_stage": self.session_stage,
                }
            progress = int(min(self.step, TOTAL_STEPS) / TOTAL_STEPS * 100)
            return {
                "state": self.status,
                "step": self.step,
                "total_steps": TOTAL_STEPS,
                "progress": progress,
            }


_jobs: dict[str, UploadJob] = {}
_registry_lock = threading.Lock()


def get_job(job_id: str) -> UploadJob | None:
    with _registry_lock:
        return _jobs.get(job_id)


def start_job(
    session_id: str,
    saved_path: Path,
    canonical_mime: str,
    *,
    settings: Settings,
    store: SessionStore,
    client: LLMClient,
) -> UploadJob:
    job = UploadJob(job_id=str(uuid.uuid4()), session_id=session_id)
    with _registry_lock:
        _jobs[job.job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job, saved_path, canonical_mime, settings, store, client),
        daemon=True,
    )
    thread.start()
    return job


def _run_job(
    job: UploadJob,
    saved_path: Path,
    canonical_mime: str,
    settings: Settings,
    store: SessionStore,
    client: LLMClient,
) -> None:
    t_start = time.perf_counter()
    try:
        with job.lock:
            job.status, job.step = "reading_document", 1
        t0 = time.perf_counter()
        # 검증 단계에서 이미 확정한 정규 MIME 으로 처리기를 나눈다(2026-09-06
        # PNG/JPEG → PDF 판독기 오분류 버그의 재발 방지 — routes_document.py 와
        # 같은 분기 로직을 그대로 옮겼다).
        if file_kind_for(canonical_mime) == "image":
            document = image_reader.read(saved_path, doc_id=saved_path.name)
        else:
            document = pdf_reader.read(saved_path, doc_id=saved_path.name, settings=settings)
        t1 = time.perf_counter()

        with job.lock:
            job.status, job.step = "checking_content", 2
        cleaned_pages = []
        for page in document.pages:
            if page.text is None:
                cleaned_pages.append(page)
                continue
            scan_report = scan_injection(page.text, settings=settings)
            cleaned_text = apply_scan(page.text, scan_report)
            masked_text, _ = mask_pii(cleaned_text)
            cleaned_pages.append(page.model_copy(update={"text": masked_text}))
        document = document.model_copy(update={"pages": tuple(cleaned_pages)})
        t2 = time.perf_counter()

        with job.lock:
            job.status, job.step = "extracting_debts", 3
        debts = extract(document, client=client)
        t3 = time.perf_counter()
        extraction = ExtractionResult(debts=tuple(debts))

        state = store.get(job.session_id)
        if state is None:
            # TTL 로 세션이 이미 지워졌다 — 느린 재시도 도중 만료된 드문 경우.
            raise RuntimeError("session_expired_during_upload_job")
        new_state = transition(state, SessionStage.S2_EXTRACTED)
        new_state = new_state.model_copy(
            update={"document": document, "extraction": extraction, "updated_at": datetime.now()}
        )
        store.save(new_state)

        with job.lock:
            job.debt_count = len(debts)
            job.session_stage = new_state.stage.value
            job.status, job.step = "ready", TOTAL_STEPS

        logger.info(
            "upload_job_timing",
            extra={
                "read": round(t1 - t0, 4),
                "mask_scan": round(t2 - t1, 4),
                "extract": round(t3 - t2, 4),
                "total": round(time.perf_counter() - t_start, 4),
            },
        )
    except DomainError as exc:
        # 문서 자체가 문제(암호화·손상 등) — 기존 동기 경로와 같은 메시지를
        # 그대로 쓴다. DomainError 의 메시지는 내부 경로를 남기지 않도록 이미
        # 검증돼 있다(ingest 모듈들의 자체 테스트).
        with job.lock:
            job.status, job.error = FAILED, str(exc)
    except Exception as exc:
        logger.warning("extraction_failed: %s: %s", type(exc).__name__, exc)
        with job.lock:
            job.status, job.error = FAILED, _EXTRACTION_FAILURE_MESSAGE
