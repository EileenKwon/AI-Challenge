"""정책 카드 출처 감시 스크립트의 순수 로직만 테스트한다.

실제 네트워크 호출(`_fetch_hash`)은 이 테스트에서 하지 않는다 — 대신
`_visible_text()`(오탐의 실제 원인이었던 부분)를 검증한다. 실측(2026-09-06):
신용회복위원회 페이지가 요청마다 CSRF 토큰 등을 HTML 태그 안에 새로 심어
내려줘서, 원문을 그대로 해싱하면 내용이 안 바뀌어도 매번 "변경"으로 오탐됐다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "tools" / "policy_watch" / "check_policy_sources.py"
)
_spec = importlib.util.spec_from_file_location("check_policy_sources", _MODULE_PATH)
_check_policy_sources = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _check_policy_sources
_spec.loader.exec_module(_check_policy_sources)

_visible_text = _check_policy_sources._visible_text


def test_visible_text_strips_tags_and_collapses_whitespace() -> None:
    html = "<html><body>  <h1>사전채무조정</h1>\n<p>연체 30일 이상 90일 이하</p></body></html>"
    assert _visible_text(html) == "사전채무조정 연체 30일 이상 90일 이하"


def test_visible_text_ignores_script_and_style_blocks() -> None:
    """script/style 안의 내용(정책과 무관)은 비교 대상에서 아예 빠져야 한다."""
    html = "<style>.x{color:red}</style><script>var csrfToken = 'abc123';</script><p>본문 내용</p>"
    assert _visible_text(html) == "본문 내용"


def test_visible_text_ignores_html_comments() -> None:
    html = "<p>본문</p><!-- session=xyz789 -->"
    assert _visible_text(html) == "본문"


def test_visible_text_is_stable_when_only_hidden_tokens_change() -> None:
    """회귀 테스트 — 실제 원인이었던 시나리오: hidden input/meta 값만 요청마다 바뀌는 경우."""
    html_a = (
        '<html><head><meta name="csrf-token" content="AAA111"></head>'
        '<body><input type="hidden" name="JSESSIONID" value="AAA111">'
        "<p>사전채무조정 안내</p></body></html>"
    )
    html_b = (
        '<html><head><meta name="csrf-token" content="ZZZ999"></head>'
        '<body><input type="hidden" name="JSESSIONID" value="ZZZ999">'
        "<p>사전채무조정 안내</p></body></html>"
    )
    assert _visible_text(html_a) == _visible_text(html_b)


def test_visible_text_detects_a_real_content_change() -> None:
    html_a = "<p>연체 30일 이상 90일 이하</p>"
    html_b = "<p>연체 30일 이상 120일 이하</p>"
    assert _visible_text(html_a) != _visible_text(html_b)
