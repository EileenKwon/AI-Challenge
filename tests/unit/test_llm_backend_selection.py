"""LLM 백엔드 선택과 json_mode 규칙."""

from __future__ import annotations

import pytest

from dn.llm.client import (
    AnthropicClient,
    OpenAICompatibleClient,
    StubClient,
    get_llm_client,
)
from dn.settings import get_settings


def _settings_with(**env_overrides):
    base = get_settings()
    return base.model_copy(update={"env": base.env.model_copy(update=env_overrides)})


def test_openai_compatible_wins_when_anthropic_key_absent() -> None:
    settings = _settings_with(
        anthropic_api_key="",
        dn_openai_base_url="https://api.groq.com/openai/v1",
        dn_openai_api_key="gsk_test",
        dn_openai_model="qwen/qwen3.8-27b",
    )
    assert isinstance(get_llm_client(settings), OpenAICompatibleClient)


def test_anthropic_still_wins_when_both_configured() -> None:
    settings = _settings_with(
        anthropic_api_key="sk-ant-test",
        dn_openai_base_url="https://api.groq.com/openai/v1",
        dn_openai_api_key="gsk_test",
        dn_openai_model="qwen/qwen3.8-27b",
    )
    assert isinstance(get_llm_client(settings), AnthropicClient)


@pytest.mark.parametrize(
    "overrides",
    [
        {"dn_openai_base_url": "https://x/v1", "dn_openai_api_key": "k"},  # 모델 없음
        {"dn_openai_base_url": "https://x/v1", "dn_openai_model": "m"},  # 키 없음
        {"dn_openai_api_key": "k", "dn_openai_model": "m"},  # base_url 없음
    ],
)
def test_partial_openai_config_falls_through_to_stub(overrides: dict) -> None:
    """세 값 중 하나라도 비면 활성화하지 않는다 — 반쯤 설정된 채로 죽지 않게."""
    settings = _settings_with(anthropic_api_key="", dn_local_model_path="", **overrides)
    assert isinstance(get_llm_client(settings), StubClient)


def test_json_mode_only_set_when_requested() -> None:
    """설명문 생성에 json_mode 가 켜지면 산문 대신 JSON 이 돌아온다.

    로컬 백엔드가 모든 호출에 JSON 강제 디코딩을 걸고 있어서 LLM 서술 경로가
    사실상 죽어 있었다 — 그 회귀를 막는다.
    """
    sent: list[dict] = []

    class _Recorder(OpenAICompatibleClient):
        def __init__(self) -> None:
            self._base_url = "https://x/v1"
            self._model = "m"
            self._api_key = "k"
            self._timeout = 5

    import httpx

    client = _Recorder()

    def fake_post(url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "usage": {}},
            request=httpx.Request("POST", url),
        )

    original = httpx.post
    httpx.post = fake_post
    try:
        client.complete(system="s", user="u")
        client.complete(system="s", user="u", json_mode=True)
    finally:
        httpx.post = original

    assert "response_format" not in sent[0]
    assert sent[1]["response_format"] == {"type": "json_object"}
