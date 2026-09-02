"""설정 로더 — `.env` 와 `config/config.yaml` 을 병합해 `Settings` 싱글턴을 만든다.

경로·임계치는 전부 여기서만 해석한다 (AGENTS.md 절대 규칙 9).
`config.yaml` 은 섹션별로 `extra="forbid"` 모델에 검증하므로, 존재하지 않는 키에
접근하면 `AttributeError` 가, 문서에 없는 키가 섞여 있으면 `ValidationError` 가
즉시 발생한다 — 조용히 `None` 을 반환하지 않는다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"


class _Env(BaseSettings):
    """`.env` 및 프로세스 환경변수에서 읽는 값."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    dn_env: str = "development"
    # 이 서비스가 LLM에 시키는 일은 (1) 1쪽짜리 조회서에서 고정 스키마 JSON 추출,
    # (2) 확정 숫자를 문장으로 옮기기 두 가지다. 둘 다 난도가 높지 않다 —
    # 로컬 오픈모델(Qwen2.5-7B)로도 E1 F1 0.9975가 나왔다.
    #
    # 기본값을 sonnet-4-6 에서 sonnet-5 로 올린다: 같은 계열의 후속 모델이면서
    # 단가가 더 싸다($3/$15 → $2/$10 per MTok). 합성문서 55건 1회 평가는
    # 문서당 대략 입력 2.5K·출력 0.6K 토큰이라 전체 $1 아래다.
    # 더 싸고 빠르게: claude-haiku-4-5($1/$5). 여유를 더: claude-opus-5($5/$25).
    # 배포 환경에서는 DN_LLM_MODEL 로 덮어쓴다.
    dn_llm_model: str = "claude-sonnet-5"
    dn_llm_timeout_sec: int = 60
    dn_secret_key: str = "change-me"
    # 빈 값 = 미설정. config.yaml 의 paths.upload_dir 을 쓴다 (Settings.upload_dir 참고).
    dn_upload_dir: str = ""
    dn_session_db: str = "./sessions.db"
    # ANTHROPIC_API_KEY 가 없을 때의 무료 폴백 — GGUF 파일 경로가 설정되고 실제
    # 존재하면 get_llm_client() 가 StubClient 대신 이 로컬 모델을 쓴다.
    # OpenAI 호환 Chat Completions 백엔드(Groq · Gemini · Upstage 등).
    # 세 값이 모두 있어야 활성화된다. 무료 티어로 배포할 때 쓰는 경로다.
    dn_openai_base_url: str = ""
    dn_openai_api_key: str = ""
    dn_openai_model: str = ""
    dn_local_model_path: str = ""
    dn_local_llm_threads: int = 0
    dn_local_llm_ctx: int = 4096


class _StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MetaConfig(_StrictModel):
    policy_base_date: str
    service_name: str


class PathsConfig(_StrictModel):
    upload_dir: str
    policy_card_dir: str
    policy_card_version: str
    safety_dir: str
    synthetic_dir: str
    questions_file: str


class SessionConfig(_StrictModel):
    ttl_minutes: int
    max_violations: int


class IngestConfig(_StrictModel):
    max_upload_mb: int
    allowed_mime: list[str]
    min_text_chars: int


class ExtractionConfig(_StrictModel):
    low_confidence_threshold: float
    max_debts: int


class ReconcileConfig(_StrictModel):
    living_cost_floor_by_household: dict[int, int]
    living_cost_check_enabled: bool

    def living_cost_floor(self, household_size: int) -> int | None:
        """가구원수에 해당하는 필수생활비 하한을 돌려준다.

        공식 기준표는 6인까지만 고시되므로, 그보다 큰 가구는 마지막 두 구간의
        증가분(6인 − 5인)을 더해 외삽한다. 표가 비어 있으면 `None` 을 돌려
        호출부가 검사를 건너뛰게 한다.
        """
        table = self.living_cost_floor_by_household
        if not table or household_size < 1:
            return None
        if household_size in table:
            return table[household_size]
        max_size = max(table)
        if household_size <= max_size:
            # 표에 구멍이 있으면 가장 가까운 하위 구간을 쓴다.
            lower = max(k for k in table if k < household_size)
            return table[lower]
        if len(table) < 2:
            return table[max_size]
        prev = max(k for k in table if k < max_size)
        step = table[max_size] - table[prev]
        return table[max_size] + step * (household_size - max_size)


class RateLimitConfig(_StrictModel):
    enabled: bool
    llm_calls_per_ip: int
    window_seconds: int


class CashflowConfig(_StrictModel):
    currency_unit: str
    dti_warn_ratio: float
    dti_severe_ratio: float


class RulesConfig(_StrictModel):
    allow_unverified_cards: bool
    max_paths: int


class NarrativeConfig(_StrictModel):
    enabled: bool
    max_retries: int
    fallback_to_template: bool


class ReportConfig(_StrictModel):
    max_pages: int
    font_family: str


class LoggingConfig(_StrictModel):
    level: str
    redact_pii: bool


class AppConfig(_StrictModel):
    """`config/config.yaml` 전체 스키마."""

    meta: MetaConfig
    paths: PathsConfig
    session: SessionConfig
    ingest: IngestConfig
    extraction: ExtractionConfig
    reconcile: ReconcileConfig
    ratelimit: RateLimitConfig
    cashflow: CashflowConfig
    rules: RulesConfig
    narrative: NarrativeConfig
    report: ReportConfig
    logging: LoggingConfig


def load_config(path: Path = _DEFAULT_CONFIG_PATH) -> AppConfig:
    """`config.yaml` 을 읽어 `AppConfig` 로 검증한다. 실패 시 명시적 예외를 던진다."""
    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)


class Settings(BaseModel):
    """앱 전역에서 참조하는 단일 설정 객체. 경로는 여기서만 해석한다."""

    model_config = ConfigDict(frozen=True)

    env: _Env
    config: AppConfig
    project_root: Path

    def resolve(self, relative: str) -> Path:
        return (self.project_root / relative).resolve()

    @property
    def upload_dir(self) -> Path:
        """업로드 원본 저장 경로. `DN_UPLOAD_DIR` 가 있으면 그쪽이 이긴다.

        이 속성은 원래 `config.yaml` 만 읽었다. 그런데 `.env.example` 과
        Dockerfile 은 `DN_UPLOAD_DIR` 를 설정하고 있었다 — 아무도 읽지 않는
        죽은 설정이었고, 컨테이너에서 쓰기 가능한 경로를 그 변수로 지정해도
        앱은 여전히 `./uploads` 를 쓰다가 PermissionError 로 죽었다.
        `DN_SESSION_DB` 는 이미 환경변수로 동작하므로 그쪽과 규칙을 맞춘다.
        """
        return self.resolve(self.env.dn_upload_dir or self.config.paths.upload_dir)

    @property
    def policy_card_dir(self) -> Path:
        base = self.resolve(self.config.paths.policy_card_dir)
        return base / self.config.paths.policy_card_version

    @property
    def safety_dir(self) -> Path:
        return self.resolve(self.config.paths.safety_dir)

    @property
    def synthetic_dir(self) -> Path:
        return self.resolve(self.config.paths.synthetic_dir)

    @property
    def questions_path(self) -> Path:
        return self.resolve(self.config.paths.questions_file)

    @property
    def session_db_path(self) -> Path:
        return self.resolve(self.env.dn_session_db)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """`Settings` 싱글턴을 반환한다. 최초 호출 시 `.env`/`config.yaml` 을 읽는다."""
    return Settings(env=_Env(), config=load_config(), project_root=_PROJECT_ROOT)
