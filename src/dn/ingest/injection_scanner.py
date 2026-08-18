"""문서 내 프롬프트 인젝션 탐지.

탐지된 라인만 제거 대상으로 보고하고 문서 전체를 거부하지 않는다.
패턴은 `config/safety/injection_patterns.yaml` 에서 읽는다.
"""

from __future__ import annotations

import re

import yaml

from dn.domain.models import ScanReport
from dn.settings import Settings, get_settings


def _load_patterns(settings: Settings) -> list[re.Pattern[str]]:
    path = settings.safety_dir / "injection_patterns.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [re.compile(p, re.IGNORECASE) for p in raw.get("patterns", [])]


def scan(text: str, *, settings: Settings | None = None) -> ScanReport:
    """텍스트를 줄 단위로 검사해 인젝션 의심 라인을 찾는다."""
    settings = settings or get_settings()
    patterns = _load_patterns(settings)

    removed_lines: list[str] = []
    matched_rules: list[str] = []

    for line in text.splitlines():
        for pattern in patterns:
            if pattern.search(line):
                removed_lines.append(line)
                if pattern.pattern not in matched_rules:
                    matched_rules.append(pattern.pattern)
                break

    return ScanReport(
        detected=bool(removed_lines),
        removed_lines=tuple(removed_lines),
        matched_rules=tuple(matched_rules),
    )


def apply(text: str, report: ScanReport) -> str:
    """`report.removed_lines` 에 담긴 라인을 제거한 텍스트를 재구성한다."""
    removed = set(report.removed_lines)
    return "\n".join(line for line in text.splitlines() if line not in removed)
