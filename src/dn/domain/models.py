"""채무회복 내비게이터 — 도메인 데이터 계약

전 계층(API, 파이프라인, 계산, 규칙, 설명 생성, 평가)이 이 타입을 공유한다.

설계 근거: ARCHITECTURE.md §5
핵심 원칙:
  - 모든 필드는 자기 출처(Provenance)를 들고 다닌다.
  - 결측은 None 으로 유지하고 UNKNOWN 으로 전파한다. 0 이나 평균으로 대체하지 않는다.
  - 금액은 Decimal(원 단위 정수)이며 float 를 허용하지 않는다.
  - 모든 모델은 불변(frozen)이다. 변경은 model_copy(update=...) 로 한다.

enums 는 `domain/enums.py`, 출처 추적 기반 타입(Base/Money/Ratio/Tracked)은
`domain/provenance.py` 에 있다.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from dn.domain.enums import (
    STAGE_ORDER,
    ActionTiming,
    ConditionState,
    PathStatus,
    ProductType,
    RepaymentType,
    SectionKind,
    SessionStage,
    TriageDecision,
)
from dn.domain.provenance import Base, Money, OpenRatio, Ratio, Tracked

# ===========================================================================
# 1. 입력 도메인
# ===========================================================================


class Debt(Base):
    """채무 1건.

    interest_rate / monthly_payment / repayment_type 은 조회서에 없다.
    추출 대상이 아니라 보완 입력 대상이다(기획서 2.2 구조적 공백).
    """

    debt_id: str
    creditor: Tracked[str] = Field(default_factory=Tracked)
    product_type: Tracked[ProductType] = Field(default_factory=Tracked)
    balance: Tracked[Money] = Field(default_factory=Tracked)
    executed_at: Tracked[date] = Field(default_factory=Tracked)
    maturity_at: Tracked[date] = Field(default_factory=Tracked)
    overdue_days: Tracked[int] = Field(default_factory=Tracked)
    is_secured: Tracked[bool] = Field(default_factory=Tracked)

    # --- 보완 입력 대상 ---
    interest_rate: Tracked[Ratio] = Field(default_factory=Tracked)  # 연이율, 0.0~1.0
    monthly_payment: Tracked[Money] = Field(default_factory=Tracked)
    repayment_type: Tracked[RepaymentType] = Field(default_factory=Tracked)


class IncomeProfile(Base):
    monthly_net_income: Tracked[Money] = Field(default_factory=Tracked)
    support_income: Tracked[Money] = Field(default_factory=Tracked)  # 정기 지원금
    income_proof_available: Tracked[bool] = Field(default_factory=Tracked)
    has_continuous_income: Tracked[bool] = Field(default_factory=Tracked)


class HouseholdProfile(Base):
    essential_living_cost: Tracked[Money] = Field(default_factory=Tracked)
    housing_cost: Tracked[Money] = Field(default_factory=Tracked)
    medical_care_cost: Tracked[Money] = Field(default_factory=Tracked)
    other_fixed_cost: Tracked[Money] = Field(default_factory=Tracked)
    dependents: Tracked[int] = Field(default_factory=Tracked)


class SituationFlags(Base):
    """조건부 추가 질문과 트리아지·복합지원 신호."""

    has_real_estate: Tracked[bool] = Field(default_factory=Tracked)
    has_vehicle: Tracked[bool] = Field(default_factory=Tracked)
    has_lease_deposit: Tracked[bool] = Field(default_factory=Tracked)
    under_collection_contact: Tracked[bool] = Field(default_factory=Tracked)
    recent_job_loss: Tracked[bool] = Field(default_factory=Tracked)
    business_closed: Tracked[bool] = Field(default_factory=Tracked)
    court_proceeding_ongoing: Tracked[bool] = Field(default_factory=Tracked)
    seizure_ongoing: Tracked[bool] = Field(default_factory=Tracked)
    has_guarantee_debt: Tracked[bool] = Field(default_factory=Tracked)
    has_tax_debt: Tracked[bool] = Field(default_factory=Tracked)
    has_private_debt: Tracked[bool] = Field(default_factory=Tracked)
    housing_arrears_risk: Tracked[bool] = Field(default_factory=Tracked)
    legal_dispute: Tracked[bool] = Field(default_factory=Tracked)


# ===========================================================================
# 2. 문서·추출
# ===========================================================================


class PageContent(Base):
    page_no: int
    text: str | None = None
    image_path: str | None = None  # 스캔본일 때만


class DocumentContent(Base):
    doc_id: str
    filename: str
    is_scanned: bool
    pages: tuple[PageContent, ...] = ()


class MaskReport(Base):
    masked_counts: dict[str, int] = Field(default_factory=dict)  # {"rrn": 1, "account": 3}

    @property
    def total(self) -> int:
        return sum(self.masked_counts.values())


class ScanReport(Base):
    """인젝션 스캔 결과. 문서 전체를 거부하지 않고 해당 라인만 제거한다."""

    detected: bool = False
    removed_lines: tuple[str, ...] = ()
    matched_rules: tuple[str, ...] = ()


class ExtractionResult(Base):
    debts: tuple[Debt, ...] = ()
    doc_total_balance: Tracked[Money] = Field(default_factory=Tracked)  # 문서상 총액
    mask_report: MaskReport | None = None
    scan_report: ScanReport | None = None
    low_confidence_fields: tuple[str, ...] = ()  # "debt_0.balance" 형식

    @property
    def all_confirmed(self) -> bool:
        """S2 → S3 전이 가능 여부."""
        for d in self.debts:
            for name in ("creditor", "product_type", "balance", "overdue_days", "is_secured"):
                tracked: Tracked = getattr(d, name)
                if not tracked.user_confirmed:
                    return False
        return True


# ===========================================================================
# 3. 누락·모순
# ===========================================================================


class Gap(Base):
    rule_id: str  # GAP_RATE, GAP_PAYMENT, ...
    label: str
    target: str  # "debt_0.interest_rate"
    impact: str  # 계산 결과에 미치는 영향


class Conflict(Base):
    rule_id: str  # CONF_BALANCE_SUM, CONF_OVERDUE, IMPL_LIVING_COST
    label: str
    values: tuple[str, ...]
    resolution: str | None = None  # "최대값 42일 채택"
    resolved: bool = False


class GapReport(Base):
    gaps: tuple[Gap, ...] = ()


class ConflictReport(Base):
    conflicts: tuple[Conflict, ...] = ()

    @property
    def has_unresolved(self) -> bool:
        return any(not c.resolved for c in self.conflicts)


class Question(Base):
    qid: str
    text: str
    kind: str  # "money" | "bool" | "int" | "choice"
    required: bool = True
    conditional_on: str | None = None
    skippable: bool = False
    skip_impact: str | None = None  # 건너뛸 경우 계산에 미치는 영향


# ===========================================================================
# 4. 계산 결과
# ===========================================================================


class CalcStep(Base):
    """계산식 추적. 화면의 '이 숫자는 어디서 왔나요' 펼치기에 그대로 쓴다."""

    label: str
    formula: str  # "2,500,000 - 1,450,000"
    inputs: dict[str, str] = Field(default_factory=dict)
    output: str


class CashflowResult(Base):
    total_debt: Money
    monthly_total_payment: Money
    monthly_available: Money
    monthly_shortfall: Money  # 양수 = 부족
    # 부담률은 100% 를 넘을 수 있어(상환액이 소득을 초과하는 상황이 이 서비스의
    # 핵심 대상) 0~1 로 제한된 Ratio 대신 상한 없는 OpenRatio 를 쓴다(T08).
    dti_ratio: OpenRatio | None = None  # 소득 미입력 또는 소득 0일 때 None
    max_overdue_days: int | None = None
    secured_ratio: Ratio | None = None
    weighted_avg_rate: Ratio | None = None
    max_rate: Ratio | None = None
    recent_debt_ratio: Ratio | None = None

    trace: tuple[CalcStep, ...] = ()
    assumptions: tuple[str, ...] = ()  # "의료비 미반영"
    excluded_items: tuple[str, ...] = ()  # "3건 중 1건의 월상환액 미입력"
    completeness: Ratio = Decimal("0")  # 핵심 필드 확보율 (기획서 14.3)


class ScenarioResult(Base):
    scenario_id: str  # "income_drop_20"
    label: str  # "소득이 20% 줄어든다면"
    before: CashflowResult
    after: CashflowResult
    note: str | None = None


# ===========================================================================
# 5. 규칙 엔진
# ===========================================================================


class PolicyRef(Base):
    card_id: str
    card_version: str
    title: str
    url: str | None = None
    policy_base_date: date
    verified: bool = False


class ConditionResult(Base):
    id: str
    label: str
    state: ConditionState
    required: bool
    evidence: str | None = None  # 판단 근거가 된 사용자 입력


class PathCandidate(Base):
    """기획서 7.2 결과 카드 11개 항목과 1:1 대응."""

    path_id: str  # 1
    name: str  # 1
    priority: int  # 2
    agency: str  # 3
    status: PathStatus
    met: tuple[ConditionResult, ...] = ()  # 4
    unknown: tuple[ConditionResult, ...] = ()  # 5
    not_met: tuple[ConditionResult, ...] = ()
    swing_factors: tuple[str, ...] = ()  # 6
    user_evidence: tuple[str, ...] = ()  # 7
    policy_ref: PolicyRef | None = None  # 8
    next_actions: tuple[str, ...] = ()  # 9
    consult_questions: tuple[str, ...] = ()  # 10
    why_final_check: str = ""  # 11
    excluded_reason: str | None = None


class TriageResult(Base):
    decision: TriageDecision
    signals: tuple[str, ...] = ()
    referral_agency: str | None = None
    message: str = ""


class RuleEngineResult(Base):
    paths: tuple[PathCandidate, ...] = ()  # 최대 3개
    excluded_paths: tuple[PathCandidate, ...] = ()
    undetermined: bool = False
    undetermined_reasons: tuple[str, ...] = ()
    rule_version: str = ""
    policy_base_date: date | None = None
    dev_mode: bool = False  # 미검증 카드 사용 시 True


# ===========================================================================
# 6. 설명·계획·리포트
# ===========================================================================


class GroundingReport(Base):
    """숫자 그라운딩 검증 결과 (T14). 허용 집합에 없는 숫자가 있으면 grounded=False."""

    grounded: bool
    ungrounded_tokens: tuple[str, ...] = ()


class FilterResult(Base):
    """출력(생성문) 안전 필터 검사 결과 (T15)."""

    passed: bool
    matched_categories: tuple[str, ...] = ()
    matched_phrases: tuple[str, ...] = ()


class InputFilterResult(Base):
    """입력(사용자 질의) 안전 필터 검사 결과 (T15)."""

    blocked: bool
    matched_categories: tuple[str, ...] = ()
    matched_phrases: tuple[str, ...] = ()


class NarrativeSection(Base):
    section: SectionKind
    text: str
    generated_by_llm: bool
    grounded: bool = True
    fallback_used: bool = False


class Narrative(Base):
    sections: tuple[NarrativeSection, ...] = ()


class ActionItem(Base):
    timing: ActionTiming
    order: int
    text: str
    reason: str | None = None
    related_agency: str | None = None


class ActionPlan(Base):
    items: tuple[ActionItem, ...] = ()
    complex_support_areas: tuple[str, ...] = ()  # 기획서 12장 복합지원 분야


class ReportOptions(Base):
    """사용자가 요약서 포함 항목을 직접 선택한다(기획서 10.2 (7))."""

    include_creditor_names: bool = True
    include_income: bool = True
    include_paths: bool = True
    include_questions: bool = True


# ===========================================================================
# 7. 최종 결과 번들
# ===========================================================================


class AnalysisResult(Base):
    """기획서 10.1 (4) 설명가능성 요건의 8개 항목을 모두 담는다.

    rules 단계가 실패해도 cashflow 는 반드시 채워진다(기획서 7.3).
    """

    session_id: str
    analyzed_at: datetime

    # 입력 계층
    extraction: ExtractionResult
    income: IncomeProfile
    household: HouseholdProfile
    flags: SituationFlags
    edit_history: tuple[str, ...] = ()

    # 산출 계층
    # T18 orchestrator 는 매 analyze() 호출마다 cashflow 를 항상 채워 반환한다(기획서 7.3).
    # Optional 인 이유는 T02: 세션이 S5 이상에서 하위 단계로 되돌아가면 저장된 analysis 의
    # cashflow/rules/narrative 를 None 으로 무효화하기 때문이다(오래된 산출물 재사용 방지).
    cashflow: CashflowResult | None = None
    scenario: ScenarioResult | None = None
    triage: TriageResult | None = None
    rules: RuleEngineResult | None = None  # REFER 또는 실패 시 None
    narrative: Narrative | None = None
    plan: ActionPlan | None = None

    # 진단 계층
    gaps: GapReport = Field(default_factory=GapReport)
    conflicts: ConflictReport = Field(default_factory=ConflictReport)
    policy_base_date: date | None = None
    dev_mode: bool = False


class SessionState(Base):
    session_id: str
    stage: SessionStage = SessionStage.S0_CONSENT
    created_at: datetime
    updated_at: datetime
    consent_at: datetime | None = None
    document: DocumentContent | None = None
    extraction: ExtractionResult | None = None
    income: IncomeProfile = Field(default_factory=IncomeProfile)
    household: HouseholdProfile = Field(default_factory=HouseholdProfile)
    flags: SituationFlags = Field(default_factory=SituationFlags)
    analysis: AnalysisResult | None = None
    violation_count: int = 0

    def at_least(self, required: SessionStage) -> bool:
        return STAGE_ORDER.index(self.stage) >= STAGE_ORDER.index(required)
