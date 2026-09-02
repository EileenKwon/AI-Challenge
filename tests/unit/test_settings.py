"""T00 — 설정 로더 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dn.settings import AppConfig, get_settings


def test_config_yaml_values_reflected_in_settings() -> None:
    settings = get_settings()
    assert settings.config.session.ttl_minutes == 60
    assert settings.config.meta.service_name == "채무회복 내비게이터"
    assert settings.config.rules.max_paths == 3
    # 배포 기준값. 정책 카드 6종이 전부 verified 로 승격된 2026-09-02 부터 false 다
    # — 이 값이 true 로 되돌아가면 미검증 카드가 결과에 섞여도 아무도 모른다.
    assert settings.config.rules.allow_unverified_cards is False


def test_unknown_key_in_config_yaml_rejected() -> None:
    raw = {
        "meta": {"policy_base_date": "2026-08-13", "service_name": "x"},
        "unexpected_section": {"a": 1},
    }
    with pytest.raises(ValidationError):
        AppConfig.model_validate(raw)


def test_missing_required_key_rejected() -> None:
    raw = {"meta": {"policy_base_date": "2026-08-13", "service_name": "x"}}
    with pytest.raises(ValidationError):
        AppConfig.model_validate(raw)


def test_accessing_nonexistent_attribute_raises() -> None:
    settings = get_settings()
    with pytest.raises(AttributeError):
        _ = settings.config.no_such_section


def test_paths_are_resolved_relative_to_project_root() -> None:
    settings = get_settings()
    assert settings.upload_dir.is_absolute()
    assert settings.policy_card_dir.name == settings.config.paths.policy_card_version
