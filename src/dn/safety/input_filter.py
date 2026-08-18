"""입력 안전 필터 — 탈옥·역할변경·시스템 프롬프트 노출 요구를 탐지한다.

`config/safety/injection_patterns.yaml`(탈옥·역할변경류)과
`config/safety/banned_phrases.yaml`(위험 조언·개인정보 요구류)을 함께
검사한다. 세션 위반 횟수는 `SessionState.violation_count` 에 누적되며,
`config.yaml: session.max_violations` 를 초과하면 자동 응답을 중단하고
공식 상담 안내로 전환해야 한다(판단은 오케스트레이터가 한다, T18).
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from dn.domain.models import InputFilterResult, SessionState
from dn.settings import Settings, get_settings

_INPUT_APPLICABLE_CATEGORIES = frozenset({"risky_advice", "privacy_request"})


def _load_injection_patterns(settings: Settings) -> list[str]:
    path = settings.safety_dir / "injection_patterns.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(raw.get("patterns", []))


def _load_banned_phrase_groups(settings: Settings) -> dict[str, Any]:
    path = settings.safety_dir / "banned_phrases.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def scan(text: str, *, settings: Settings | None = None) -> InputFilterResult:
    """사용자 질의에서 탈옥·역할변경·시스템 프롬프트 노출 요구·위험 조언 요청을 탐지한다."""
    settings = settings or get_settings()

    matched_categories: list[str] = []
    matched_phrases: list[str] = []

    for pattern in _load_injection_patterns(settings):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            matched_categories.append("injection_or_jailbreak")
            matched_phrases.append(match.group())

    for category, spec in _load_banned_phrase_groups(settings).items():
        if category not in _INPUT_APPLICABLE_CATEGORIES:
            continue
        for pattern in spec.get("patterns", []):
            match = re.search(pattern, text)
            if match:
                matched_categories.append(category)
                matched_phrases.append(match.group())

    return InputFilterResult(
        blocked=bool(matched_phrases),
        matched_categories=tuple(dict.fromkeys(matched_categories)),
        matched_phrases=tuple(matched_phrases),
    )


def register_violation(state: SessionState) -> SessionState:
    """세션 위반 횟수를 1 증가시킨 새 `SessionState` 를 반환한다 (원본은 변경하지 않는다)."""
    return state.model_copy(update={"violation_count": state.violation_count + 1})


def is_session_exhausted(state: SessionState, *, settings: Settings | None = None) -> bool:
    """세션 위반 횟수가 허용치를 초과했는지 확인한다."""
    settings = settings or get_settings()
    return state.violation_count > settings.config.session.max_violations
