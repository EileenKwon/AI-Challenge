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


def test_verified_cards_have_real_sources() -> None:
    """verified: true 카드는 반드시 실제 출처 URL과 조회일자를 가져야 한다.

    이 테스트의 원래 의도는 "공식 출처 대조 없이 verified 로 올리지 않는다"였다.
    2026-08-21 대조 완료로 카드 상태가 바뀌었으므로, 상태를 고정하는 대신
    그 의도 자체를 불변조건으로 검사한다.
    """
    cards = load_all_cards()
    verified = [c for c in cards if c.verified]
    assert verified, "검증된 카드가 하나도 없습니다 — 대조 결과가 반영되지 않았습니다."
    for c in verified:
        url = c.source.get("url")
        retrieved = c.source.get("retrieved_at")
        assert url and url != "TODO", f"{c.id}: 출처 URL 미기재"
        assert url.startswith("http"), f"{c.id}: 출처 URL 형식 오류 — {url!r}"
        assert retrieved and retrieved != "TODO", f"{c.id}: 조회일자 미기재"


def test_unverified_cards_are_explicitly_documented() -> None:
    """미검증 카드는 이유가 문서화되어 있어야 한다.

    개인워크아웃은 총채무액 한도가 공식 출처 간 상이하여 확정 인코딩을 보류한 상태다.
    미검증 상태를 방치가 아니라 '기록된 판단'으로 유지하는 것이 이 테스트의 목적이다.
    """
    import yaml

    cards = load_all_cards()
    unverified = [c for c in cards if not c.verified]
    root = Path(__file__).resolve().parents[2] / "config" / "policy_cards" / "v2026-08-13"
    for c in unverified:
        raw = yaml.safe_load((root / f"{c.id}.yaml").read_text(encoding="utf-8"))
        assert raw.get("unresolved"), f"{c.id}: 미검증 사유(unresolved)가 기록되지 않았습니다."


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
