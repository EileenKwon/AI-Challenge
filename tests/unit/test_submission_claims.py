"""제출 문서의 레드팀 수치가 실측 결과와 일치하는지 지킨다.

사람이 요약을 손으로 옮기다 "위험 조언 유도 9/9, 문서 인젝션 3/3"(= 12건처럼
읽힘)으로 부풀린 적이 있다. 실측은 총 9건이고 인젝션 3건은 그 안에 포함된다.
문서가 스스로 "실측값과 표본 수를 병기한다"를 원칙으로 내걸었으므로, 그 원칙을
테스트로 고정한다.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RESULT = _ROOT / "results" / "e6_safety_redteam.csv"
_DOCS = (
    _ROOT / "docs" / "제출" / "기획서_양식본.md",
    _ROOT / "docs" / "제출" / "기능명세서_양식본.md",
)


def _measured() -> tuple[int, Counter[str]]:
    with _RESULT.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return len(rows), Counter(r["case_id"].split("-")[0] for r in rows)


@pytest.mark.parametrize("doc", _DOCS, ids=lambda p: p.name)
def test_redteam_claim_matches_measurement(doc: Path) -> None:
    if not _RESULT.exists():  # 평가 결과 미생성 환경에서는 검증할 대상이 없다
        pytest.skip(f"{_RESULT} 없음")

    total, by_kind = _measured()
    text = doc.read_text(encoding="utf-8")

    assert f"레드팀 공격 {total}건" in text, f"{doc.name}: 총 {total}건 표기가 없다"
    assert f"문서 인젝션 {by_kind['DI']}" in text, f"{doc.name}: 인젝션 건수 불일치"
    # 인젝션을 총계와 별개인 것처럼 병기하던 옛 표기가 되살아나지 않게 막는다.
    assert "9/9" not in text, f"{doc.name}: 총계를 부풀리는 옛 표기가 남아 있다"
