from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from atv_player.ai.models import AICompletionResult, AIError, AIProviderConfig

logger = logging.getLogger(__name__)
_LOG_EXTRA = {"log_category": "ai", "log_source": "app"}


class OpenAICompatibleError(AIError):
    pass


def _completion_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise OpenAICompatibleError("AI API 地址不能为空")
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _models_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise OpenAICompatibleError("AI API 地址不能为空")
    if normalized.endswith("/v1"):
        return f"{normalized}/models"
    return f"{normalized}/v1/models"


def _sanitize_message(message: str, api_key: str) -> str:
    sanitized = str(message or "")
    if api_key:
        sanitized = sanitized.replace(api_key, "[redacted]")
    return sanitized


def _endpoint_summary(url: str) -> str:
    parsed = urlsplit(str(url or ""))
    if not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/")
    return f"{parsed.hostname or parsed.netloc}{path}"


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


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
        max_tokens: int | None = None,
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
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        completion_url = _completion_url(self._config.base_url)
        endpoint = _endpoint_summary(completion_url)
        logger.info(
            "AI chat_completion request started model=%s endpoint=%s",
            payload["model"],
            endpoint,
            extra=_LOG_EXTRA,
        )
        started_at = time.perf_counter()
        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(
                    completion_url,
                    headers={"Authorization": f"Bearer {self._config.api_key.strip()}"},
                    json=payload,
                )
                response.raise_for_status()
            logger.info(
                "AI chat_completion request succeeded model=%s endpoint=%s status=%s elapsed_ms=%s",
                payload["model"],
                endpoint,
                response.status_code,
                _elapsed_ms(started_at),
                extra=_LOG_EXTRA,
            )
        except httpx.HTTPStatusError as exc:
            body = _sanitize_message(exc.response.text, self._config.api_key)
            logger.warning(
                "AI chat_completion request failed model=%s endpoint=%s status=%s elapsed_ms=%s error=%s",
                payload["model"],
                endpoint,
                exc.response.status_code,
                _elapsed_ms(started_at),
                body,
                extra=_LOG_EXTRA,
            )
            raise OpenAICompatibleError(
                f"AI API 请求失败: HTTP {exc.response.status_code} {body}"
            ) from exc
        except httpx.HTTPError as exc:
            message = _sanitize_message(str(exc), self._config.api_key)
            logger.warning(
                "AI chat_completion request failed model=%s endpoint=%s status= elapsed_ms=%s error=%s",
                payload["model"],
                endpoint,
                _elapsed_ms(started_at),
                message,
                extra=_LOG_EXTRA,
            )
            raise OpenAICompatibleError(f"AI API 请求失败: {message}") from exc
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise OpenAICompatibleError("AI API 响应缺少 choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else ""
        return AICompletionResult(content=str(content or ""), raw=data)

    def list_models(self) -> list[str]:
        api_key = self._config.api_key.strip()
        base_url = self._config.base_url
        if not base_url.strip() or not api_key:
            raise OpenAICompatibleError("AI API 配置不完整")
        models_url = _models_url(base_url)
        endpoint = _endpoint_summary(models_url)
        logger.info(
            "AI list_models request started endpoint=%s",
            endpoint,
            extra=_LOG_EXTRA,
        )
        started_at = time.perf_counter()
        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.get(
                    models_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
            logger.info(
                "AI list_models request succeeded endpoint=%s status=%s elapsed_ms=%s",
                endpoint,
                response.status_code,
                _elapsed_ms(started_at),
                extra=_LOG_EXTRA,
            )
        except httpx.HTTPStatusError as exc:
            body = _sanitize_message(exc.response.text, api_key)
            logger.warning(
                "AI list_models request failed endpoint=%s status=%s elapsed_ms=%s error=%s",
                endpoint,
                exc.response.status_code,
                _elapsed_ms(started_at),
                body,
                extra=_LOG_EXTRA,
            )
            raise OpenAICompatibleError(
                f"AI 模型列表请求失败: HTTP {exc.response.status_code} {body}"
            ) from exc
        except httpx.HTTPError as exc:
            message = _sanitize_message(str(exc), api_key)
            logger.warning(
                "AI list_models request failed endpoint=%s status= elapsed_ms=%s error=%s",
                endpoint,
                _elapsed_ms(started_at),
                message,
                extra=_LOG_EXTRA,
            )
            raise OpenAICompatibleError(f"AI 模型列表请求失败: {message}") from exc
        data = response.json()
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise OpenAICompatibleError("AI 模型列表响应缺少 data")
        models: list[str] = []
        for item in items:
            model_id = item.get("id") if isinstance(item, dict) else ""
            model_text = str(model_id or "").strip()
            if model_text:
                models.append(model_text)
        return models

    def check_connectivity(self) -> bool:
        self.chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": "Reply with OK.",
                }
            ],
            temperature=0.0,
            max_tokens=4,
        )
        return True
