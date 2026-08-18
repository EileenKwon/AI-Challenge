"""계산에 필요한데 아직 확인되지 않은 값 탐지. LLM 미사용.

금리·월상환액은 신용정보조회서에 없는 항목이라 추출 직후 상태에서는
항상 결측이며, 3단계 보완 입력을 통해 채워진다(기획서 2.2/3단계).
"""

from __future__ import annotations

from dn.domain.models import Debt, Gap, GapReport, IncomeProfile


def detect_gaps(debts: tuple[Debt, ...], income: IncomeProfile) -> GapReport:
    """채무 목록과 소득 정보에서 계산에 필요한 결측 항목을 찾는다."""
    gaps: list[Gap] = []

    for i, debt in enumerate(debts):
        if debt.interest_rate.value is None:
            gaps.append(
                Gap(
                    rule_id="GAP_RATE",
                    label="금리 미확인",
                    target=f"debt_{i}.interest_rate",
                    impact="현금흐름 계산에는 영향이 없으나 상담 시 상환구조 파악에 필요합니다.",
                )
            )
        if debt.monthly_payment.value is None:
            gaps.append(
                Gap(
                    rule_id="GAP_PAYMENT",
                    label="월 상환액 미확인",
                    target=f"debt_{i}.monthly_payment",
                    impact="이 채무는 월 상환액 합계 계산에서 제외됩니다.",
                )
            )
        if debt.executed_at.value is None:
            gaps.append(
                Gap(
                    rule_id="GAP_EXECUTED_AT",
                    label="대출실행일 미확인",
                    target=f"debt_{i}.executed_at",
                    impact="최근 신규채무 비율 계산에서 이 채무를 판단할 수 없습니다.",
                )
            )

    if income.income_proof_available.value is None:
        gaps.append(
            Gap(
                rule_id="GAP_INCOME_PROOF",
                label="소득증빙 가능 여부 미확인",
                target="income.income_proof_available",
                impact="제도 조건 중 소득 요건 판정이 UNKNOWN 으로 남습니다.",
            )
        )

    return GapReport(gaps=tuple(gaps))
