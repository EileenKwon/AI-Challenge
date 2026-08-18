"""출력 안전 필터 — 확정 표현·낙인 표현·위험 조언을 출력 단계에서 차단한다.

`confirmatory` 규칙은 제도 설명 섹션(PATH/PLAN)에만 적용한다. 현금흐름
섹션의 확정 표현("매달 13만 원이 부족합니다")은 허용되어야 한다. 그래서
`section` 없이 호출 가능한 API를 만들지 않는다.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from dn.domain.enums import SectionKind
from dn.domain.models import FilterResult
from dn.settings import Settings, get_settings


def _load_banned_phrases(settings: Settings) -> dict[str, Any]:
    path = settings.safety_dir / "banned_phrases.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def check(text: str, section: SectionKind, *, settings: Settings | None = None) -> FilterResult:
    """`text` 를 `section` 기준으로 검사한다. `section` 은 필수 인자다."""
    settings = settings or get_settings()
    groups = _load_banned_phrases(settings)

    matched_categories: list[str] = []
    matched_phrases: list[str] = []

    for category, spec in groups.items():
        applies_to = spec.get("applies_to", [])
        if "all" not in applies_to and section.value not in applies_to:
            continue
        for pattern in spec.get("patterns", []):
            match = re.search(pattern, text)
            if match:
                matched_categories.append(category)
                matched_phrases.append(match.group())

    return FilterResult(
        passed=not matched_phrases,
        matched_categories=tuple(dict.fromkeys(matched_categories)),
        matched_phrases=tuple(matched_phrases),
    )
