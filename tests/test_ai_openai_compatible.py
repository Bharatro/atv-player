from __future__ import annotations

import json

import httpx
import pytest

from atv_player.ai.models import AIProviderConfig
from atv_player.ai.openai_compatible import (
    OpenAICompatibleClient,
    OpenAICompatibleError,
)


def test_chat_completion_posts_to_normalized_v1_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "{\"mode\":\"smart_discovery\"}"}}
                ]
            },
        )

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com",
            api_key="sk-test",
            chat_model="model-a",
            timeout_seconds=12,
        ),
        transport=httpx.MockTransport(handler),
    )

    result = client.chat_completion(
        messages=[{"role": "user", "content": "类似黑镜"}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-test"
    assert captured["json"]["model"] == "model-a"
    assert result.content == "{\"mode\":\"smart_discovery\"}"


def test_chat_completion_preserves_existing_v1_base_url() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com/v1/",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    client.chat_completion(messages=[{"role": "user", "content": "x"}])

    assert urls == ["https://api.example.com/v1/chat/completions"]


def test_list_models_gets_normalized_v1_models_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "gpt-4o-mini"},
                    {"id": "gpt-4.1-mini"},
                    {"id": ""},
                    {"object": "model"},
                ]
            },
        )

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    assert client.list_models() == ["gpt-4o-mini", "gpt-4.1-mini"]
    assert captured["url"] == "https://api.example.com/v1/models"
    assert captured["auth"] == "Bearer sk-test"


def test_check_connectivity_uses_chat_completion_model() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com",
            api_key="sk-test",
            chat_model="gpt-4o-mini",
        ),
        transport=httpx.MockTransport(handler),
    )

    result = client.check_connectivity()

    assert result is True
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-4o-mini"
    assert captured["json"]["max_tokens"] == 4


def test_chat_completion_raises_sanitized_error_without_api_key() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key sk-test"}})

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        client.chat_completion(messages=[{"role": "user", "content": "x"}])

    assert "401" in str(exc_info.value)
    assert "sk-test" not in str(exc_info.value)


def test_chat_completion_logs_success_without_prompt_or_api_key(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "secret-response"}}]},
        )

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://user:pass@api.example.com/v1?token=secret-query",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("INFO", logger="atv_player.ai.openai_compatible"):
        client.chat_completion(messages=[{"role": "user", "content": "secret prompt"}])

    messages = [record.getMessage() for record in caplog.records]
    joined = "\n".join(messages)
    assert "AI chat_completion request started" in joined
    assert "AI chat_completion request succeeded" in joined
    assert "model-a" in joined
    assert "api.example.com/v1" in joined
    assert "status=200" in joined
    assert "elapsed_ms=" in joined
    assert "secret prompt" not in joined
    assert "secret-response" not in joined
    assert "sk-test" not in joined
    assert "user:pass" not in joined
    assert "secret-query" not in joined
    for record in caplog.records:
        assert getattr(record, "log_category", "") == "ai"
        assert getattr(record, "log_source", "") == "app"
