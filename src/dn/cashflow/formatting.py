"""표시용 포맷터. 계산 모듈(`calculator.py`)과 분리한다.

`compute()` 는 항상 원 단위 정수 `Decimal` 을 반환하고, 이 모듈은 그 값을
"4,600만 원", "47.2%" 같은 사람이 읽는 문자열로만 변환한다. 반대로 여기서
계산은 하지 않는다.
"""

from __future__ import annotations

from decimal import Decimal

_UNKNOWN_LABEL = "확인되지 않음"
_EOK = Decimal("100000000")
_MAN = Decimal("10000")


def format_won(amount: Decimal | None) -> str:
    """`46000000` → "4,600만 원". `None` 은 "확인되지 않음" 으로 표시한다."""
    if amount is None:
        return _UNKNOWN_LABEL

    sign = "-" if amount < 0 else ""
    magnitude = abs(amount)

    eok, remainder = divmod(magnitude, _EOK)
    man, won = divmod(remainder, _MAN)

    parts: list[str] = []
    if eok:
        parts.append(f"{eok:,.0f}억")
    if man:
        parts.append(f"{man:,.0f}만")
    if won or not parts:
        parts.append(f"{won:,.0f}")

    return f"{sign}{' '.join(parts)} 원"


def format_ratio(ratio: Decimal | None) -> str:
    """`Decimal('0.472')` → "47.2%". `None` 은 "확인되지 않음" 으로 표시한다."""
    if ratio is None:
        return _UNKNOWN_LABEL
    percent = (ratio * Decimal("100")).quantize(Decimal("0.1"))
    return f"{percent}%"


_RATIO_PLAIN_BUCKETS: tuple[tuple[Decimal, str], ...] = (
    (Decimal("0.1"), "버는 돈에 비해 빚 갚는 부담이 크지 않습니다"),
    (Decimal("0.3"), "버는 돈의 일부가 빚 갚는 데 들어갑니다"),
    (Decimal("0.5"), "버는 돈의 절반 가까이가 빚 갚는 데 들어갑니다"),
    (Decimal("0.7"), "버는 돈의 절반 이상이 빚 갚는 데 들어갑니다"),
    (Decimal("1.0"), "버는 돈의 대부분이 빚 갚는 데 들어갑니다"),
)
_RATIO_PLAIN_OVERFLOW = "벌어들이는 돈보다 갚아야 할 돈이 더 많습니다"


def format_ratio_plain(ratio: Decimal | None) -> str:
    """부담률을 쉬운 말 한 문장으로 바꾼다. 접근성 "쉬운 말 모드" 전용.

    LLM을 쓰지 않는다 — 확정 숫자(부담률)의 구간을 나누는 순수 함수다.
    구간 경계는 `_RATIO_PLAIN_BUCKETS` 에 오름차순으로 고정돼 있다.
    """
    if ratio is None:
        return _UNKNOWN_LABEL
    for threshold, sentence in _RATIO_PLAIN_BUCKETS:
        if ratio < threshold:
            return sentence
    return _RATIO_PLAIN_OVERFLOW
