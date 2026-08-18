"""T10 — 정책 카드 스키마와 로더 테스트."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dn.domain.errors import PolicyCardError
from dn.rules.policy_card import load_all_cards, load_usable_cards
from dn.settings import Settings, get_settings

_REAL_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "config" / "policy_cards" / "_schema.yaml"


def _settings_with(
    base: Settings, *, policy_card_dir: str, version: str, allow_unverified: bool
) -> Settings:
    paths = base.config.paths.model_copy(
        update={"policy_card_dir": policy_card_dir, "policy_card_version": version}
    )
    rules = base.config.rules.model_copy(update={"allow_unverified_cards": allow_unverified})
    config = base.config.model_copy(update={"paths": paths, "rules": rules})
    return base.model_copy(update={"config": config})


def _make_card_dir(tmp_path: Path, version: str) -> Path:
    root = tmp_path / "policy_cards"
    version_dir = root / version
    version_dir.mkdir(parents=True)
    shutil.copy(_REAL_SCHEMA_PATH, root / "_schema.yaml")
    return root


_VALID_CARD = """
id: test_card
version: "2026-08-13.1"
name: 테스트 카드
agency: 테스트기관
verified: true
policy_base_date: "2026-08-13"
source:
  title: "테스트 출처"
  url: "https://example.com"
  retrieved_at: "2026-08-13"
conditions:
  - id: c1
    label: 테스트 조건
    field: max_overdue_days
    op: gte
    value: 0
    required: true
"""

_UNVERIFIED_CARD = _VALID_CARD.replace("verified: true", "verified: false").replace(
    "test_card", "test_card_unverified"
)

_INVALID_CARD = """
id: broken_card
name: 스키마 위반 카드
conditions: []
"""


# --- 실제 6개 카드 -------------------------------------------------------------


def test_all_six_real_policy_cards_pass_schema_validation() -> None:
    cards = load_all_cards()
    assert len(cards) == 6
    ids = {c.id for c in cards}
    assert ids == {
        "sinsok_debt_adjustment",
        "pre_debt_adjustment",
        "personal_workout",
        "creditor_negotiation",
        "court_rehabilitation",
        "complex_support",
    }


def test_real_cards_are_all_unverified_by_design() -> None:
    """공식 출처 대조 전이므로 6개 전부 verified: false 여야 한다."""
    cards = load_all_cards()
    assert all(c.verified is False for c in cards)


# --- 스키마 위반 카드 거부 ------------------------------------------------------


def test_schema_violating_card_is_rejected(tmp_path: Path) -> None:
    root = _make_card_dir(tmp_path, "v1")
    (root / "v1" / "broken.yaml").write_text(_INVALID_CARD, encoding="utf-8")

    settings = _settings_with(
        get_settings(), policy_card_dir=str(root), version="v1", allow_unverified=True
    )
    with pytest.raises(PolicyCardError):
        load_all_cards(settings=settings)


# --- verified: false 기본 제외 --------------------------------------------------


def test_unverified_card_excluded_when_flag_disabled(tmp_path: Path) -> None:
    root = _make_card_dir(tmp_path, "v1")
    (root / "v1" / "unverified.yaml").write_text(_UNVERIFIED_CARD, encoding="utf-8")

    settings = _settings_with(
        get_settings(), policy_card_dir=str(root), version="v1", allow_unverified=False
    )
    with pytest.raises(PolicyCardError):
        load_usable_cards(settings=settings)


def test_verified_card_included_when_flag_disabled(tmp_path: Path) -> None:
    root = _make_card_dir(tmp_path, "v1")
    (root / "v1" / "unverified.yaml").write_text(_UNVERIFIED_CARD, encoding="utf-8")
    (root / "v1" / "valid.yaml").write_text(_VALID_CARD, encoding="utf-8")

    settings = _settings_with(
        get_settings(), policy_card_dir=str(root), version="v1", allow_unverified=False
    )
    usable, dev_mode = load_usable_cards(settings=settings)
    assert len(usable) == 1
    assert usable[0].id == "test_card"
    assert dev_mode is False


# --- dev_mode 플래그 동작 -------------------------------------------------------


def test_dev_mode_true_when_unverified_cards_included(tmp_path: Path) -> None:
    root = _make_card_dir(tmp_path, "v1")
    (root / "v1" / "unverified.yaml").write_text(_UNVERIFIED_CARD, encoding="utf-8")

    settings = _settings_with(
        get_settings(), policy_card_dir=str(root), version="v1", allow_unverified=True
    )
    usable, dev_mode = load_usable_cards(settings=settings)
    assert len(usable) == 1
    assert dev_mode is True


def test_dev_mode_false_when_only_verified_cards_present(tmp_path: Path) -> None:
    root = _make_card_dir(tmp_path, "v1")
    (root / "v1" / "valid.yaml").write_text(_VALID_CARD, encoding="utf-8")

    settings = _settings_with(
        get_settings(), policy_card_dir=str(root), version="v1", allow_unverified=True
    )
    usable, dev_mode = load_usable_cards(settings=settings)
    assert dev_mode is False


def test_no_usable_cards_raises_policy_card_error(tmp_path: Path) -> None:
    root = _make_card_dir(tmp_path, "v1")
    settings = _settings_with(
        get_settings(), policy_card_dir=str(root), version="v1", allow_unverified=True
    )
    with pytest.raises(PolicyCardError):
        load_usable_cards(settings=settings)


def test_missing_version_directory_raises() -> None:
    settings = _settings_with(
        get_settings(),
        policy_card_dir="./config/policy_cards",
        version="v9999-does-not-exist",
        allow_unverified=True,
    )
    with pytest.raises(PolicyCardError):
        load_all_cards(settings=settings)
