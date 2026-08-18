"""세션 상태머신 — 7개 화면의 흐름을 강제한다.

전이 규칙:
  - 전진: 인접한 다음 단계로만 허용한다 (건너뛰기 금지).
  - 후진: 임의의 이전 단계로 허용한다 (사용자가 되돌아가 수정하는 경우).
  - `S2_EXTRACTED → S3_CONFIRMED` 는 추출된 모든 필드가 사용자 확인을
    마쳤을 때만 허용한다.
  - `S5_ANALYZED` 이상에서 하위 단계로 되돌아가면 저장된 분석 결과의
    `cashflow`/`rules`/`narrative` 를 무효화한다.
"""

from __future__ import annotations

from dn.domain.enums import STAGE_ORDER, SessionStage
from dn.domain.errors import StateTransitionError
from dn.domain.models import SessionState


def can_transition(from_stage: SessionStage, to_stage: SessionStage) -> bool:
    """`from_stage` → `to_stage` 전이가 전이표상 허용되는지만 판단한다.

    필드별 부가 조건(예: 추출 확인 여부)은 검사하지 않는다. `transition()` 이 담당한다.
    """
    if from_stage == to_stage:
        return False
    from_idx = STAGE_ORDER.index(from_stage)
    to_idx = STAGE_ORDER.index(to_stage)
    if to_idx == from_idx + 1:
        return True
    return to_idx < from_idx


def assert_at_least(state: SessionState, required: SessionStage) -> None:
    """`state.stage` 가 `required` 이상이 아니면 `StateTransitionError` 를 던진다."""
    if not state.at_least(required):
        raise StateTransitionError(
            f"필요한 최소 단계 {required.value} 에 도달하지 않았습니다 (현재: {state.stage.value})"
        )


def transition(state: SessionState, to_stage: SessionStage) -> SessionState:
    """검증을 거쳐 `to_stage` 로 전이한 새 `SessionState` 를 반환한다.

    원본 `state` 는 변경하지 않는다 (frozen 모델).
    """
    if not can_transition(state.stage, to_stage):
        raise StateTransitionError(
            f"허용되지 않은 전이입니다: {state.stage.value} → {to_stage.value}"
        )

    if state.stage == SessionStage.S2_EXTRACTED and to_stage == SessionStage.S3_CONFIRMED:
        extraction = state.extraction
        if extraction is None or not extraction.all_confirmed:
            raise StateTransitionError(
                "추출된 모든 필드가 사용자 확인을 완료해야 S3_CONFIRMED 로 전이할 수 있습니다."
            )

    update: dict[str, object] = {"stage": to_stage}

    from_idx = STAGE_ORDER.index(state.stage)
    to_idx = STAGE_ORDER.index(to_stage)
    is_rollback_from_s5_or_above = to_idx < from_idx and from_idx >= STAGE_ORDER.index(
        SessionStage.S5_ANALYZED
    )
    if is_rollback_from_s5_or_above and state.analysis is not None:
        update["analysis"] = state.analysis.model_copy(
            update={"cashflow": None, "rules": None, "narrative": None}
        )

    return state.model_copy(update=update)
