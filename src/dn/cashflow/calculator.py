"""현금흐름 계산 — 기획서 8.2 계산식을 결정론적으로 구현한다. 오차 0이 요구사항이다.

순수 함수 모듈이다. LLM·DB·파일·난수·현재 시각을 참조하지 않는다
(AGENTS.md 절대 규칙 10). 기준일이 필요해지면 인자로 받는다.

계산식:
  월 가용재원 = 월 실수령소득 + 정기 지원금 − 필수생활비 − 주거비 − 의료·돌봄비 − 기타 필수 고정비
  월 부족액   = 현재 월 예정 상환액 − 월 가용재원
  부담률      = 현재 월 예정 상환액 ÷ 월 실수령소득
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from dn.domain.models import CalcStep, CashflowResult, Debt, HouseholdProfile, IncomeProfile

_ZERO = Decimal("0")

# "상담에 필요한 핵심 필드" (기획서 14.3 입력 완성도) — 이 계산식이 직접 소비하는
# 필드만 core 로 본다: 소득, 필수생활비, 그리고 채무별 잔액·월상환액.
_HOUSEHOLD_CORE_FIELD = "essential_living_cost"


def _fmt(value: Decimal) -> str:
    return f"{value:,}"


def _label_for(debt: Debt, index: int) -> str:
    return debt.creditor.value or f"채무 {index + 1}"


def _sum_known(values: list[Decimal]) -> Decimal:
    return sum(values, _ZERO)


def _split_debt_field(
    debts: tuple[Debt, ...], *, field: str, missing_reason: str
) -> tuple[Decimal, tuple[str, ...]]:
    """채무 목록에서 `field` 값이 확인된 것만 모아 합계와, 제외된 항목 사유를 반환한다."""
    known: list[Decimal] = []
    excluded: list[str] = []
    for i, debt in enumerate(debts):
        tracked = getattr(debt, field)
        if tracked.value is None:
            excluded.append(f"{_label_for(debt, i)}: {missing_reason}")
        else:
            known.append(tracked.value)
    return _sum_known(known), tuple(excluded)


def _optional(value: Decimal | None, *, label: str, assumptions: list[str]) -> Decimal:
    """선택 항목이 미입력이면 0으로 처리하고 assumptions 에 기록한다."""
    if value is None:
        assumptions.append(f"{label} 미입력 — 0으로 처리")
        return _ZERO
    return value


def _max_overdue_days(debts: tuple[Debt, ...]) -> int | None:
    known = [d.overdue_days.value for d in debts if d.overdue_days.value is not None]
    return max(known) if known else None


def _core_field_ratio(
    debts: tuple[Debt, ...], income: IncomeProfile, household: HouseholdProfile
) -> Decimal:
    """핵심 필드 확보율 = 확인된 핵심 필드 수 / 전체 핵심 필드 수."""
    core_flags = [
        income.monthly_net_income.value is not None,
        getattr(household, _HOUSEHOLD_CORE_FIELD).value is not None,
    ]
    for debt in debts:
        core_flags.append(debt.balance.value is not None)
        core_flags.append(debt.monthly_payment.value is not None)

    if not core_flags:
        return Decimal("1")
    known = sum(1 for flag in core_flags if flag)
    return (Decimal(known) / Decimal(len(core_flags))).quantize(Decimal("0.001"))


def _secured_ratio(debts: tuple[Debt, ...], total_debt: Decimal) -> Decimal | None:
    """담보채무 비중. 잔액이나 담보 여부가 하나라도 미확인이면 None."""
    if not debts or total_debt <= _ZERO:
        return None
    secured = _ZERO
    for d in debts:
        if d.balance.value is None or d.is_secured.value is None:
            return None
        if d.is_secured.value:
            secured += d.balance.value
    return secured / total_debt


def _rate_stats(debts: tuple[Debt, ...]) -> tuple[Decimal | None, Decimal | None]:
    """(가중평균금리, 최고금리). 금리가 확인된 채무만으로 계산하고, 하나도 없으면 (None, None)."""
    rated = [d for d in debts if d.interest_rate.value is not None and d.balance.value is not None]
    if not rated:
        return None, None
    weight = _sum_known([d.balance.value for d in rated])
    if weight <= _ZERO:
        return None, max(d.interest_rate.value for d in rated)
    weighted = _sum_known([d.balance.value * d.interest_rate.value for d in rated]) / weight
    return weighted, max(d.interest_rate.value for d in rated)


def _recent_debt_ratio(
    debts: tuple[Debt, ...],
    total_debt: Decimal,
    *,
    as_of: date | None,
    has_recent_debt: bool | None = None,
) -> Decimal | None:
    """최근 6개월 이내 실행된 채무 원금의 비중.

    신용회복위원회 제도 공통 조건("최근 6개월 이내 새로 생긴 채무 원금이 총 채무원금의
    30% 미만")을 평가하려면 이 값이 필요하다.

    기준일(`as_of`)이 없거나 실행일이 하나라도 미확인이면 파생 계산이 불가능하다 —
    일부만으로 비율을 내면 "모른다"가 "충족"으로 둔갑한다. 이 모듈은 현재 시각을
    참조하지 않으므로(AGENTS.md 절대 규칙 10) 기준일은 반드시 인자로 받는다.

    `has_recent_debt` 는 보완입력 Q5_RECENT_DEBT 의 답이다. 파생 계산이 불가능할 때만
    쓰이며, **"없다"(False)만** 비율 0 으로 받는다. "있다"(True)는 금액을 모르므로
    비율을 만들 수 없어 미확인으로 남긴다 — 자기신고로 조건을 충족시키는 방향은
    열지 않는다.
    """
    derived = _derived_recent_debt_ratio(debts, total_debt, as_of=as_of)
    if derived is not None:
        return derived
    if has_recent_debt is False:
        return _ZERO
    return None


def _derived_recent_debt_ratio(
    debts: tuple[Debt, ...], total_debt: Decimal, *, as_of: date | None
) -> Decimal | None:
    if as_of is None or not debts or total_debt <= _ZERO:
        return None
    cutoff = as_of - timedelta(days=182)  # 6개월
    recent = _ZERO
    for d in debts:
        if d.balance.value is None or d.executed_at.value is None:
            return None
        if d.executed_at.value >= cutoff:
            recent += d.balance.value
    return recent / total_debt


def compute(
    debts: tuple[Debt, ...],
    income: IncomeProfile,
    household: HouseholdProfile,
    *,
    as_of: date | None = None,
    has_recent_debt: bool | None = None,
) -> CashflowResult:
    """채무·소득·가구 정보로부터 확정 현금흐름 숫자를 산출한다.

    `as_of` 는 "최근 6개월 신규채무 비율" 계산의 기준일이다. 이 모듈은 현재 시각을
    참조하지 않으므로 호출부가 넘겨야 하며, 넘기지 않으면 해당 비율은 `None`(미확인)이 된다.

    `has_recent_debt` 는 같은 비율을 파생 계산할 수 없을 때의 보완입력 답변이다.
    자세한 처리는 `_recent_debt_ratio()` 참고.
    """
    assumptions: list[str] = []

    total_debt, balance_excluded = _split_debt_field(
        debts, field="balance", missing_reason="잔액 미입력으로 총채무액 합계에서 제외"
    )
    monthly_total_payment, payment_excluded = _split_debt_field(
        debts, field="monthly_payment", missing_reason="월상환액 미입력으로 합계에서 제외"
    )
    excluded_items = balance_excluded + payment_excluded

    net_income = _optional(
        income.monthly_net_income.value, label="월 실수령소득", assumptions=assumptions
    )
    support_income = _optional(
        income.support_income.value, label="정기 지원금", assumptions=assumptions
    )
    living_cost = _optional(
        household.essential_living_cost.value, label="필수생활비", assumptions=assumptions
    )
    housing_cost = _optional(household.housing_cost.value, label="주거비", assumptions=assumptions)
    medical_cost = _optional(
        household.medical_care_cost.value, label="의료·돌봄비", assumptions=assumptions
    )
    other_cost = _optional(
        household.other_fixed_cost.value, label="기타 필수 고정비", assumptions=assumptions
    )

    monthly_available = (
        net_income + support_income - living_cost - housing_cost - medical_cost - other_cost
    )
    monthly_shortfall = monthly_total_payment - monthly_available

    trace: list[CalcStep] = [
        CalcStep(
            label="총 채무액",
            formula=" + ".join(_fmt(d.balance.value) for d in debts if d.balance.value is not None)
            or "0",
            inputs={
                f"debt_{i}.balance": _fmt(d.balance.value)
                for i, d in enumerate(debts)
                if d.balance.value is not None
            },
            output=_fmt(total_debt),
        ),
        CalcStep(
            label="월 총 예정 상환액",
            formula=" + ".join(
                _fmt(d.monthly_payment.value) for d in debts if d.monthly_payment.value is not None
            )
            or "0",
            inputs={
                f"debt_{i}.monthly_payment": _fmt(d.monthly_payment.value)
                for i, d in enumerate(debts)
                if d.monthly_payment.value is not None
            },
            output=_fmt(monthly_total_payment),
        ),
        CalcStep(
            label="월 가용재원",
            formula=(
                f"{_fmt(net_income)} + {_fmt(support_income)} - {_fmt(living_cost)} - "
                f"{_fmt(housing_cost)} - {_fmt(medical_cost)} - {_fmt(other_cost)}"
            ),
            inputs={
                "monthly_net_income": _fmt(net_income),
                "support_income": _fmt(support_income),
                "essential_living_cost": _fmt(living_cost),
                "housing_cost": _fmt(housing_cost),
                "medical_care_cost": _fmt(medical_cost),
                "other_fixed_cost": _fmt(other_cost),
            },
            output=_fmt(monthly_available),
        ),
        CalcStep(
            label="월 부족액",
            formula=f"{_fmt(monthly_total_payment)} - {_fmt(monthly_available)}",
            inputs={
                "monthly_total_payment": _fmt(monthly_total_payment),
                "monthly_available": _fmt(monthly_available),
            },
            output=_fmt(monthly_shortfall),
        ),
    ]

    dti_ratio: Decimal | None = None
    raw_income = income.monthly_net_income.value
    if raw_income is not None and raw_income != 0:
        dti_ratio = (monthly_total_payment / raw_income).quantize(Decimal("0.001"))
        trace.append(
            CalcStep(
                label="부담률",
                formula=f"{_fmt(monthly_total_payment)} / {_fmt(raw_income)}",
                inputs={
                    "monthly_total_payment": _fmt(monthly_total_payment),
                    "monthly_net_income": _fmt(raw_income),
                },
                output=str(dti_ratio),
            )
        )

    weighted_avg_rate, max_rate = _rate_stats(debts)

    return CashflowResult(
        total_debt=total_debt,
        monthly_total_payment=monthly_total_payment,
        monthly_available=monthly_available,
        monthly_shortfall=monthly_shortfall,
        dti_ratio=dti_ratio,
        max_overdue_days=_max_overdue_days(debts),
        secured_ratio=_secured_ratio(debts, total_debt),
        weighted_avg_rate=weighted_avg_rate,
        max_rate=max_rate,
        recent_debt_ratio=_recent_debt_ratio(
            debts, total_debt, as_of=as_of, has_recent_debt=has_recent_debt
        ),
        trace=tuple(trace),
        assumptions=tuple(assumptions),
        excluded_items=excluded_items,
        completeness=_core_field_ratio(debts, income, household),
    )
