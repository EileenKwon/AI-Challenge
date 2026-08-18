"""전 계층이 공유하는 열거형.

설계 근거: ARCHITECTURE.md §5
"""

from __future__ import annotations

from enum import StrEnum


class FieldSource(StrEnum):
    """필드 값의 출처. 기획서 10.1 (4) 설명가능성 요건."""

    DOCUMENT = "document"  # 문서에서 AI가 추출
    USER_INPUT = "user_input"  # 사용자가 직접 입력
    USER_EDIT = "user_edit"  # AI 추출값을 사용자가 수정
    DERIVED = "derived"  # 계산 모듈 산출
    UNKNOWN = "unknown"  # 미확인


class ProductType(StrEnum):
    """조회서의 다양한 채무 유형 표기를 정규화한 표준 분류."""

    CREDIT_LOAN = "credit_loan"  # 신용대출
    CARD_LOAN = "card_loan"  # 카드론
    CASH_ADVANCE = "cash_advance"  # 현금서비스
    INSTALLMENT = "installment"  # 할부금융
    REVOLVING = "revolving"  # 리볼빙
    SECURED_LOAN = "secured_loan"  # 담보대출
    GUARANTEE = "guarantee"  # 보증채무
    OTHER = "other"


class RepaymentType(StrEnum):
    EQUAL_PRINCIPAL_INTEREST = "equal_principal_interest"  # 원리금균등
    EQUAL_PRINCIPAL = "equal_principal"  # 원금균등
    INTEREST_ONLY = "interest_only"  # 만기일시(이자만)
    BULLET = "bullet"  # 만기일시
    OTHER = "other"


class ConditionState(StrEnum):
    """3-state. UNKNOWN 을 NOT_MET 으로 취급하는 것은 금지."""

    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"


class PathStatus(StrEnum):
    CANDIDATE = "candidate"  # 우선 검토 가능
    NEEDS_INFO = "needs_info"  # 일부 충족, 추가 확인 필요
    EXCLUDED = "excluded"  # 제외
    UNDETERMINED = "undetermined"  # 판정 불가


class SessionStage(StrEnum):
    """7개 화면과 1:1 대응하는 상태머신."""

    S0_CONSENT = "s0_consent"
    S1_UPLOADED = "s1_uploaded"
    S2_EXTRACTED = "s2_extracted"
    S3_CONFIRMED = "s3_confirmed"  # 인간 감독 지점 1
    S4_SUPPLEMENTED = "s4_supplemented"
    S5_ANALYZED = "s5_analyzed"
    S6_PLANNED = "s6_planned"
    S7_REPORTED = "s7_reported"  # 인간 감독 지점 2


STAGE_ORDER: list[SessionStage] = list(SessionStage)


class SectionKind(StrEnum):
    """출력 필터의 적용 범위 구분.

    CASHFLOW 섹션에서는 확정 표현이 허용되어야 한다(기획서 1장).
    PATH 섹션에서만 확정 표현을 차단한다.
    """

    CASHFLOW = "cashflow"
    PATH = "path"
    PLAN = "plan"
    REPORT = "report"


class TriageDecision(StrEnum):
    PROCEED = "proceed"
    REFER = "refer"  # 전문상담 우선 연결 (기획서 3.2)


class ActionTiming(StrEnum):
    TODAY = "today"
    D1 = "d1"
    D2 = "d2"
    BEFORE_CONSULT = "before_consult"
    AFTER_CONSULT = "after_consult"
