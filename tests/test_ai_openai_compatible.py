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
