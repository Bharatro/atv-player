from __future__ import annotations

from typing import Any

import httpx

from atv_player.ai.models import AICompletionResult, AIError, AIProviderConfig


class OpenAICompatibleError(AIError):
    pass


def _completion_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise OpenAICompatibleError("AI API 地址不能为空")
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _sanitize_message(message: str, api_key: str) -> str:
    sanitized = str(message or "")
    if api_key:
        sanitized = sanitized.replace(api_key, "[redacted]")
    return sanitized


class OpenAICompatibleClient:
    def __init__(
        self,
        config: AIProviderConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        response_format: dict[str, object] | None = None,
    ) -> AICompletionResult:
        if not self._config.is_complete:
            raise OpenAICompatibleError("AI API 配置不完整")
        payload: dict[str, Any] = {
            "model": self._config.chat_model.strip(),
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = dict(response_format)
        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(
                    _completion_url(self._config.base_url),
                    headers={"Authorization": f"Bearer {self._config.api_key.strip()}"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = _sanitize_message(exc.response.text, self._config.api_key)
            raise OpenAICompatibleError(
                f"AI API 请求失败: HTTP {exc.response.status_code} {body}"
            ) from exc
        except httpx.HTTPError as exc:
            message = _sanitize_message(str(exc), self._config.api_key)
            raise OpenAICompatibleError(f"AI API 请求失败: {message}") from exc
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise OpenAICompatibleError("AI API 响应缺少 choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else ""
        return AICompletionResult(content=str(content or ""), raw=data)
