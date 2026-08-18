"""T16 — 7일 행동계획 테스트. 4개 우선순위 조정 규칙과 LLM 없이 완전한 생성."""

from __future__ import annotations

from dn.planning.action_plan import build_plan


def _baseline(**overrides):
    params = dict(
        max_overdue_days=10,
        income_proof_available=True,
        debts_incomplete=False,
        income_drop_signal=False,
    )
    params.update(overrides)
    return build_plan(**params)


def _text_at(plan, index: int) -> str:
    return plan.items[index].text


def test_plan_is_complete_without_llm() -> None:
    plan = _baseline()
    assert len(plan.items) == 7
    assert all(item.text for item in plan.items)
    assert [item.order for item in plan.items] == list(range(1, 8))


# --- 4개 조정 규칙 ---------------------------------------------------------------


def test_overdue_imminent_moves_consultation_booking_to_top() -> None:
    baseline = _baseline()
    assert "상담 예약" not in _text_at(baseline, 0)

    for days in (25, 30, 85, 89):
        plan = _baseline(max_overdue_days=days)
        assert "상담 예약" in _text_at(plan, 0), f"{days}일에서 상담 예약이 최상단이 아님"


def test_overdue_not_imminent_does_not_boost_booking() -> None:
    for days in (10, 24, 31, 84, 90):
        plan = _baseline(max_overdue_days=days)
        assert "상담 예약" not in _text_at(plan, 0)


def test_unknown_income_proof_moves_document_prep_up() -> None:
    baseline = _baseline()
    baseline_index = next(i for i, item in enumerate(baseline.items) if "서류 준비" in item.text)

    plan = _baseline(income_proof_available=None)
    boosted_index = next(i for i, item in enumerate(plan.items) if "서류 준비" in item.text)

    assert boosted_index < baseline_index


def test_incomplete_debt_list_moves_check_up() -> None:
    plan = _baseline(debts_incomplete=True)
    assert _text_at(plan, 0) == "추출된 채무 목록과 연체일수 확인"


def test_income_drop_signal_adds_complex_support_item() -> None:
    baseline = _baseline()
    assert baseline.complex_support_areas == ()
    assert not any("복합지원" in item.text for item in baseline.items)

    plan = _baseline(income_drop_signal=True)
    assert any("복합지원" in item.text for item in plan.items)
    assert plan.complex_support_areas != ()


def test_no_signal_does_not_add_complex_support_item() -> None:
    plan = _baseline(income_drop_signal=False)
    assert len(plan.items) == 7


# --- 결합 시나리오 ---------------------------------------------------------------


def test_multiple_triggers_combine() -> None:
    plan = _baseline(max_overdue_days=27, income_proof_available=None, income_drop_signal=True)
    assert "상담 예약" in _text_at(plan, 0)
    assert any("복합지원" in item.text for item in plan.items)


def test_action_items_come_only_from_template_not_fabricated() -> None:
    from pathlib import Path

    import yaml

    templates_path = Path(__file__).resolve().parents[2] / "config" / "action_templates.yaml"
    raw = yaml.safe_load(templates_path.read_text(encoding="utf-8"))
    allowed_texts = {item["text"] for item in raw["items"]}
    allowed_texts |= {c["text"] for c in raw.get("conditional_items", [])}

    plan = _baseline(income_drop_signal=True)
    for item in plan.items:
        assert item.text in allowed_texts
