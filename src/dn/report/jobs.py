"""상담용 요약서 PDF 생성 — 비동기 작업(job) 관리.

`POST /report` 는 PDF 를 직접 만들어 돌려주지 않는다. WeasyPrint 렌더링이
수백 ms~수 초 걸릴 수 있어(폰트 서브셋 캐시가 없는 첫 요청은 더 걸린다),
요청을 즉시 202 로 받아넘기고 실제 작업은 백그라운드 스레드에서 진행한다 —
이벤트 루프나 요청을 처리하는 스레드를 오래 붙잡지 않기 위해서다.

작업은 프로세스 메모리에만 존재한다(재시작하면 사라진다). 상담용 요약서는
`analysis`(이미 세션에 영속화된 데이터)로부터 언제든 결정론적으로 다시 만들 수
있으므로, 재시작으로 캐시가 비어도 사용자는 다시 만들기만 하면 된다 — 별도
영속 저장소를 두지 않는다.

캐싱 키는 `(session_id, options_hash, state_hash)` 세 가지다. `state_hash` 는
`analysis` 내용의 해시라 실제 분석 결과가 바뀌지 않는 한(옵션만 바뀌어도)
재사용된다 — 세션이 `/analyze`·`/plan` 을 다시 거치기 전까지는 매 `updated_at`
갱신([`supplement`] 등 무관한 저장)에 캐시가 무효화되지 않는다.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dn.domain.enums import SessionStage
from dn.domain.errors import StateTransitionError
from dn.domain.models import AnalysisResult, ReportOptions
from dn.pipeline.stages import transition
from dn.report import summary_pdf
from dn.settings import Settings
from dn.storage.session_store import SessionStore

logger = logging.getLogger(__name__)

STEP_NAMES = ("preparing_data", "rendering_html", "rendering_pdf", "ready")
TOTAL_STEPS = len(STEP_NAMES)  # 1 준비 · 2 HTML · 3 PDF · 4 완료
FAILED = "failed"

_FAILURE_MESSAGE = "요약서를 생성하지 못했습니다. 다시 시도해 주세요."


@dataclass
class ReportJob:
    job_id: str
    session_id: str
    options_hash: str
    state_hash: str
    status: str = "preparing_data"
    step: int = 1
    pdf_bytes: bytes | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.perf_counter)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def to_status_dict(self) -> dict[str, Any]:
        with self.lock:
            if self.status == FAILED:
                return {"state": FAILED, "error": self.error}
            progress = int(min(self.step, TOTAL_STEPS) / TOTAL_STEPS * 100)
            return {
                "state": self.status,
                "step": self.step,
                "total_steps": TOTAL_STEPS,
                "progress": progress,
            }


_jobs: dict[str, ReportJob] = {}
_cache_index: dict[tuple[str, str, str], str] = {}
_registry_lock = threading.Lock()


def compute_options_hash(options: ReportOptions) -> str:
    return hashlib.sha256(options.model_dump_json().encode()).hexdigest()[:16]


def compute_state_hash(analysis: AnalysisResult) -> str:
    return hashlib.sha256(analysis.model_dump_json().encode()).hexdigest()[:16]


def get_job(job_id: str) -> ReportJob | None:
    with _registry_lock:
        return _jobs.get(job_id)


def get_or_create_job(
    session_id: str,
    analysis: AnalysisResult,
    options: ReportOptions,
    *,
    settings: Settings,
    store: SessionStore,
) -> tuple[ReportJob, bool]:
    """캐시된 완료 작업이 있으면 재사용하고, 없으면 새로 시작한다.

    반환값의 두 번째 요소는 "새로 시작했는가"다.
    """
    options_hash = compute_options_hash(options)
    state_hash = compute_state_hash(analysis)
    cache_key = (session_id, options_hash, state_hash)

    with _registry_lock:
        cached_job_id = _cache_index.get(cache_key)
        if cached_job_id is not None:
            cached = _jobs.get(cached_job_id)
            if cached is not None and cached.status == "ready":
                return cached, False

        job = ReportJob(
            job_id=str(uuid.uuid4()),
            session_id=session_id,
            options_hash=options_hash,
            state_hash=state_hash,
        )
        _jobs[job.job_id] = job

    thread = threading.Thread(
        target=_run_job, args=(job, analysis, options, settings, store, cache_key), daemon=True
    )
    thread.start()
    return job, True


def _mark_session_reported(store: SessionStore, session_id: str) -> None:
    """작업이 성공한 시점에만 S6→S7 전이를 시도한다.

    이미 S7_REPORTED 면(옵션을 바꿔 다시 만든 경우) 조용히 건너뛴다 — 상태
    전이는 세션 생애주기에서 한 번만 일어나야 하고, PDF 재생성 자체는 그와
    무관하게 여러 번 허용된다. 동시에 두 작업이 경쟁해도(드묾) 두 번째
    시도는 `StateTransitionError` 를 그냥 무시한다 — PDF 는 이미 만들어졌으므로
    사용자에게는 실패로 보이면 안 된다.
    """
    state = store.get(session_id)
    if state is None or state.stage == SessionStage.S7_REPORTED:
        return
    try:
        new_state = transition(state, SessionStage.S7_REPORTED)
    except StateTransitionError:
        return
    store.save(new_state.model_copy(update={"updated_at": datetime.now()}))


def _run_job(
    job: ReportJob,
    analysis: AnalysisResult,
    options: ReportOptions,
    settings: Settings,
    store: SessionStore,
    cache_key: tuple[str, str, str],
) -> None:
    t_start = time.perf_counter()
    try:
        with job.lock:
            job.status, job.step = "preparing_data", 1
        t0 = time.perf_counter()
        context = summary_pdf.build_context(analysis, options, settings=settings)
        t1 = time.perf_counter()

        with job.lock:
            job.status, job.step = "rendering_html", 2
        html = summary_pdf.render_html_from_context(context)
        t2 = time.perf_counter()

        with job.lock:
            job.status, job.step = "rendering_pdf", 3
        pdf_bytes = summary_pdf.render_pdf_from_html(html)
        t3 = time.perf_counter()

        _mark_session_reported(store, job.session_id)

        with job.lock:
            job.pdf_bytes = pdf_bytes
            job.status, job.step = "ready", TOTAL_STEPS

        with _registry_lock:
            _cache_index[cache_key] = job.job_id

        # PII·PDF 내용은 남기지 않는다 — 단계별 소요 시간만 기록한다.
        logger.info(
            "report_timing",
            extra={
                "data": round(t1 - t0, 4),
                "html": round(t2 - t1, 4),
                "weasyprint": round(t3 - t2, 4),
                "write": 0.0,  # 파일로 쓰지 않고 메모리에서 바로 응답한다
                "llm": 0.0,  # s6_planned 데이터를 그대로 포맷팅 — LLM 재호출 없음
                "total": round(t3 - t_start, 4),
            },
        )
    except Exception as exc:
        logger.warning("report_generation_failed", extra={"exception_class": type(exc).__name__})
        with job.lock:
            job.status, job.error = FAILED, _FAILURE_MESSAGE
