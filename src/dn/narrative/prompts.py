"""설명 생성 프롬프트 — 값을 문장으로 옮기는 재서술 과제로 제한한다.

LLM 에 원본 문서 텍스트, 정책 카드 원문 전체, PII, 규칙 엔진 내부 조건식을
넘기지 않는다. 이미 계산·판정이 끝난 확정 값만 전달한다.
"""

from __future__ import annotations

from typing import Any

NARRATIVE_SYSTEM_PROMPT = (
    "당신은 주어진 값을 자연스러운 한국어 문장으로 옮기는 재서술 도우미다. "
    "새로운 숫자, 조건, 기관명, 자격 판정을 만들어내지 마라. "
    "주어진 값에 없는 내용은 절대 추가하지 마라. "
    "확정적인 표현(신청 가능합니다, 승인됩니다 등)을 쓰지 마라."
)


def build_cashflow_prompt(cashflow_summary: dict[str, Any]) -> str:
    """현금흐름 확정 숫자를 문장으로 재서술하도록 요청하는 사용자 프롬프트."""
    lines = "\n".join(f"- {k}: {v}" for k, v in cashflow_summary.items())
    return (
        "다음 값을 있는 그대로 자연스러운 문장으로 옮겨라. "
        "숫자를 새로 만들거나 반올림하지 마라.\n\n" + lines
    )


def build_path_prompt(path_summaries: list[dict[str, Any]]) -> str:
    """제도 경로 후보를 문장으로 재서술하도록 요청하는 사용자 프롬프트."""
    blocks = "\n\n".join("\n".join(f"- {k}: {v}" for k, v in p.items()) for p in path_summaries)
    return (
        "다음 제도 경로 후보를 있는 그대로 문장으로 옮겨라. "
        "신청 가능 여부를 확정하지 마라.\n\n" + blocks
    )
