"""도메인 예외.

src/dn/** 전 계층은 bare except 대신 이 계층의 예외로 래핑한다 (AGENTS.md §2.1).
"""

from __future__ import annotations


class DomainError(Exception):
    """모든 도메인 예외의 기반 클래스."""


class StateTransitionError(DomainError):
    """세션 상태머신에서 허용되지 않은 전이를 시도했다."""


class PolicyCardError(DomainError):
    """정책 카드 스키마 검증 실패 또는 사용 가능한 카드가 0개다."""


class GroundingError(DomainError):
    """생성된 문장에 허용 집합 밖의 숫자가 등장했다."""


class ExtractionError(DomainError):
    """LLM 추출 결과가 재시도 후에도 스키마 검증에 실패했다."""


class SafetyViolationError(DomainError):
    """세션의 안전 필터 위반 횟수가 허용치를 초과했다."""
