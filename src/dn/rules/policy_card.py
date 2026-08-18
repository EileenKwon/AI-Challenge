"""정책 카드 로더 — YAML 을 스키마 검증하고 `verified` 게이트를 적용한다.

제도 조건은 코드에 두지 않고 전부 `config/policy_cards/**.yaml` 에 둔다
(AGENTS.md 절대 규칙 5). `verified: false` 카드는 기본적으로 제외되며,
`config.yaml: rules.allow_unverified_cards` 가 true 일 때만 포함된다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import yaml
from pydantic import BaseModel, ConfigDict

from dn.domain.errors import PolicyCardError
from dn.settings import Settings, get_settings

_SCHEMA_FILENAME = "_schema.yaml"


class PolicyCondition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    id: str
    label: str
    field: str
    op: str
    value: Any = None
    required: bool = True


class PolicyCard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    id: str
    version: str
    name: str
    agency: str
    target: str | None = None
    priority: int = 999
    verified: bool
    policy_base_date: str
    source: dict[str, Any]
    conditions: list[PolicyCondition]
    exclusions: list[dict[str, Any]] = []
    required_inputs: list[str] = []
    documents: list[str] = []
    consult_questions: list[str] = []
    swing_factors: list[str] = []
    why_final_check: str = ""


def _version_dir(settings: Settings, version: str | None) -> Path:
    base = settings.resolve(settings.config.paths.policy_card_dir)
    return base / (version or settings.config.paths.policy_card_version)


def _load_schema(base_dir: Path) -> dict[str, Any]:
    schema_path = base_dir.parent / _SCHEMA_FILENAME
    if not schema_path.exists():
        raise PolicyCardError(f"정책 카드 스키마 파일을 찾을 수 없습니다: {schema_path}")
    return yaml.safe_load(schema_path.read_text(encoding="utf-8"))


def _iter_card_files(version_dir: Path) -> list[Path]:
    if not version_dir.exists():
        raise PolicyCardError(f"정책 카드 디렉토리를 찾을 수 없습니다: {version_dir}")
    return sorted(p for p in version_dir.glob("*.yaml") if p.name != _SCHEMA_FILENAME)


def load_all_cards(
    *, version: str | None = None, settings: Settings | None = None
) -> list[PolicyCard]:
    """지정한 버전(기본: `config.yaml` 설정값) 아래 모든 카드를 로드하고 스키마를 검증한다.

    스키마를 위반한 카드가 있으면 `PolicyCardError` 를 던진다.
    """
    settings = settings or get_settings()
    version_dir = _version_dir(settings, version)
    schema = _load_schema(version_dir)

    cards: list[PolicyCard] = []
    for path in _iter_card_files(version_dir):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(instance=raw, schema=schema)
        except jsonschema.ValidationError as exc:
            raise PolicyCardError(f"정책 카드 스키마 위반: {path.name} ({exc.message})") from exc
        cards.append(PolicyCard.model_validate(raw))
    return cards


def load_usable_cards(
    *, version: str | None = None, settings: Settings | None = None
) -> tuple[list[PolicyCard], bool]:
    """평가에 사용할 카드 목록과 `dev_mode` 여부를 반환한다.

    `allow_unverified_cards` 가 false 면 `verified: true` 카드만 남기고,
    true 면 전부 포함하되 그중 미검증 카드가 하나라도 있으면 `dev_mode=True`.
    사용 가능한 카드가 0개면 `PolicyCardError`.
    """
    settings = settings or get_settings()
    all_cards = load_all_cards(version=version, settings=settings)

    if settings.config.rules.allow_unverified_cards:
        usable = all_cards
        dev_mode = any(not c.verified for c in usable)
    else:
        usable = [c for c in all_cards if c.verified]
        dev_mode = False

    if not usable:
        raise PolicyCardError("사용 가능한 정책 카드가 없습니다 (verified 카드 0개).")

    return usable, dev_mode
