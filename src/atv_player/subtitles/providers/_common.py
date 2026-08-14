"""字幕站 provider 共用的 HTTP 与错误收敛逻辑。

各 provider 通过注入的 ``get`` / ``post`` 发请求（应用侧传入的是代理感知的可调用
对象，见 app.py 的 ``_proxy_http_get()``），单测里换成假函数即可离线跑。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from atv_player.subtitles.errors import (
    SubtitleBlockedError,
    SubtitleProviderError,
    SubtitleQuotaExceededError,
)

BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15.0
DOWNLOAD_TIMEOUT = 30.0

_BLOCK_MARKERS = (
    "网站防火墙",
    "访问认证",
    "请输入验证码",
    "cf-browser-verification",
    "checking your browser",
    "just a moment",
    "attention required",
)


def merge_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if extra:
        headers.update(extra)
    return headers


def clean_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    return {key: value for key, value in params.items() if value not in (None, "", [])}


def _status_code(response: object) -> int:
    try:
        return int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _raise_for_status(response: object, site: str) -> None:
    code = _status_code(response)
    if code == 429:
        raise SubtitleQuotaExceededError(f"{site}请求过于频繁，请稍后再试")
    if code in (401, 403):
        raise SubtitleBlockedError(
            f"{site}拒绝了请求（{code}），可能需要重新配置或被风控"
        )
    if code and not 200 <= code < 400:
        raise SubtitleProviderError(f"{site}返回异常状态码 {code}")


def raise_for_status(response: object, site: str) -> None:
    """公开版状态码检查，配合 ``ignore_status`` 使用的调用方手动触发。"""
    _raise_for_status(response, site)


def guard_blocked(text: str, site: str) -> None:
    """抓取站命中验证码/风控时给出明确文案，而不是当成"没搜到"。"""
    lowered = text[:4000].casefold()
    if any(marker in lowered for marker in _BLOCK_MARKERS):
        raise SubtitleBlockedError(f"{site}触发了验证码，暂时无法搜索")


def http_get(
    get: Callable[..., Any],
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    site: str = "",
    ignore_status: bool = False,
) -> Any:
    """发 GET 请求并做统一的错误收敛。

    ``ignore_status=True`` 时不检查 HTTP 状态码，给"错误信息在响应体里"
    的站点（如射手网把错误码漏进状态码）用，调用方自行解析后再调
    :func:`raise_for_status` 兜底。
    """
    kwargs: dict[str, Any] = {
        "params": clean_params(params),
        "headers": merge_headers(headers),
        "timeout": timeout,
        "follow_redirects": True,
    }
    if cookies:
        kwargs["cookies"] = cookies
    try:
        response = get(url, **kwargs)
    except (SubtitleProviderError, SubtitleQuotaExceededError, SubtitleBlockedError):
        raise
    except Exception as exc:
        raise SubtitleProviderError(f"{site}请求失败: {exc}") from exc
    if not ignore_status:
        _raise_for_status(response, site)
    return response


def http_post(
    post: Callable[..., Any],
    url: str,
    *,
    data: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    site: str = "",
) -> Any:
    kwargs: dict[str, Any] = {
        "headers": merge_headers(headers),
        "timeout": timeout,
        "follow_redirects": True,
    }
    if cookies:
        kwargs["cookies"] = cookies
    if data is not None:
        kwargs["data"] = data
    if json_body is not None:
        kwargs["json"] = json_body
    try:
        response = post(url, **kwargs)
    except (SubtitleProviderError, SubtitleQuotaExceededError, SubtitleBlockedError):
        raise
    except Exception as exc:
        raise SubtitleProviderError(f"{site}请求失败: {exc}") from exc
    _raise_for_status(response, site)
    return response


def response_json(response: object, site: str) -> dict[str, Any]:
    try:
        payload = response.json()  # type: ignore[attr-defined]
    except Exception as exc:
        raise SubtitleProviderError(f"{site}返回的不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise SubtitleProviderError(f"{site}返回了非预期的数据结构")
    return payload


def response_text(response: object) -> str:
    text = getattr(response, "text", "")
    return text if isinstance(text, str) else ""


def response_bytes(response: object) -> bytes:
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8", errors="replace")
    return b""
