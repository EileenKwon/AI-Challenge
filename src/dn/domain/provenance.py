"""출처 추적 기반 타입.

전 계층이 공유하는 최소 공통 기반이다. `enums` 에만 의존하며 `models` 에는
의존하지 않는다 (순환 임포트 방지).

핵심 원칙:
  - 금액은 `Decimal`(원 단위 정수)이며 `float` 를 허용하지 않는다.
  - 비율은 0.0~1.0 `Decimal` 이다.
  - 모든 모델은 불변(frozen)이다. 변경은 `model_copy(update=...)` 로 한다.
  - 값 + 출처를 `Tracked[T]` 로 함께 들고 다닌다. `value is None` 이면 UNKNOWN 이며
    계산에서 제외된다.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict

from dn.domain.enums import FieldSource

T = TypeVar("T")


class Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _to_money(v: Any) -> Decimal:
    """금액 검증: float 금지, 원 단위 정수만 허용."""
    if isinstance(v, float):
        raise ValueError("금액에 float 를 사용할 수 없습니다. Decimal 또는 int 를 쓰세요.")
    if isinstance(v, Decimal):
        d = v
    elif isinstance(v, (int, str)):
        d = Decimal(str(v))
    else:
        raise ValueError(f"금액으로 변환할 수 없는 타입: {type(v)}")
    if d != d.to_integral_value():
        raise ValueError("금액은 원 단위 정수여야 합니다.")
    return d.to_integral_value()


def _to_ratio(v: Any) -> Decimal:
    """비율 검증: 0.0 ~ 1.0. 퍼센트가 아니다."""
    if isinstance(v, float):
        raise ValueError("비율에 float 를 사용할 수 없습니다. Decimal 또는 문자열을 쓰세요.")
    d = v if isinstance(v, Decimal) else Decimal(str(v))
    if not (Decimal("0") <= d <= Decimal("1")):
        raise ValueError(f"비율은 0.0~1.0 범위여야 합니다: {d}")
    return d


def _to_open_ratio(v: Any) -> Decimal:
    """상한 없는 비율 검증: float 금지, 음수만 거부한다.

    부담률(dti_ratio) 처럼 100% 를 넘을 수 있는 값에 쓴다 — 채무자의 상환 부담이
    소득을 초과하는 상황이 이 서비스의 핵심 대상이므로 1.0 상한을 두면 그 상황을
    표현할 수 없다.
    """
    if isinstance(v, float):
        raise ValueError("비율에 float 를 사용할 수 없습니다. Decimal 또는 문자열을 쓰세요.")
    d = v if isinstance(v, Decimal) else Decimal(str(v))
    if d < Decimal("0"):
        raise ValueError(f"비율은 음수일 수 없습니다: {d}")
    return d


Money = Annotated[Decimal, BeforeValidator(_to_money)]
Ratio = Annotated[Decimal, BeforeValidator(_to_ratio)]
OpenRatio = Annotated[Decimal, BeforeValidator(_to_open_ratio)]


class Tracked(Base, Generic[T]):
    """값 + 출처. `value is None` 이면 UNKNOWN 이며 계산에서 제외된다."""

    value: T | None = None
    source: FieldSource = FieldSource.UNKNOWN
    confidence: Decimal | None = None  # DOCUMENT 일 때만 의미 있음
    page: int | None = None  # 문서 근거 위치
    raw_text: str | None = None  # 원문 스니펫 (설명가능성)
    edited_at: datetime | None = None
    user_confirmed: bool = False

    @property
    def is_known(self) -> bool:
        return self.value is not None

    @classmethod
    def unknown(cls) -> Tracked[T]:
        return cls(value=None, source=FieldSource.UNKNOWN)
