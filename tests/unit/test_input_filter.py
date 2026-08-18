"""T15 — 입력 안전 필터 테스트. data/redteam/attacks.yaml 전량 차단 확인."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dn.domain.enums import SessionStage
from dn.domain.models import SessionState
from dn.safety.input_filter import is_session_exhausted, register_violation, scan
from dn.settings import get_settings

_ATTACKS_PATH = Path(__file__).resolve().parents[2] / "data" / "redteam" / "attacks.yaml"


def _all_attack_texts() -> list[tuple[str, str]]:
    raw = yaml.safe_load(_ATTACKS_PATH.read_text(encoding="utf-8"))
    cases = list(raw["document_injection"]) + list(raw["user_query"])
    return [(c["id"], c["text"]) for c in cases]


@pytest.mark.parametrize("case_id,text", _all_attack_texts())
def test_all_redteam_attack_samples_are_blocked(case_id: str, text: str) -> None:
    result = scan(text)
    assert result.blocked is True, f"{case_id} 가 차단되지 않았습니다: {text!r}"


def test_benign_query_is_not_blocked() -> None:
    result = scan("사전채무조정은 어떤 서류가 필요한가요?")
    assert result.blocked is False
    assert result.matched_phrases == ()


def _session(**overrides) -> SessionState:
    from datetime import datetime

    base = dict(
        session_id="s1",
        stage=SessionStage.S5_ANALYZED,
        created_at=datetime(2026, 8, 18),
        updated_at=datetime(2026, 8, 18),
    )
    base.update(overrides)
    return SessionState(**base)


def test_register_violation_increments_and_does_not_mutate_original() -> None:
    state = _session(violation_count=0)
    new_state = register_violation(state)
    assert new_state.violation_count == 1
    assert state.violation_count == 0


def test_session_not_exhausted_within_limit() -> None:
    settings = get_settings()
    assert settings.config.session.max_violations == 3
    state = _session(violation_count=3)
    assert is_session_exhausted(state, settings=settings) is False


def test_session_exhausted_when_exceeding_limit() -> None:
    settings = get_settings()
    state = _session(violation_count=4)
    assert is_session_exhausted(state, settings=settings) is True
