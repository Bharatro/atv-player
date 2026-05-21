from __future__ import annotations

from urllib.parse import urlparse

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
HUYA_LIVE_USER_AGENT = "HYSDK(Windows,30000002)_APP(pc_exe&7080000&official)_SDK(trans&2.34.0.5795)"


def normalize_media_request_headers(url: str, headers: dict[str, str] | None = None) -> dict[str, str]:
    normalized = dict(headers or {})
    hostname = (urlparse(url).hostname or "").lower()
    if hostname.endswith("xhscdn.com"):
        normalized.setdefault("Referer", "https://www.xiaohongshu.com/")
        normalized.setdefault("User-Agent", BROWSER_USER_AGENT)
    if hostname == "huya.com" or hostname.endswith(".huya.com"):
        normalized.setdefault("Referer", "https://www.huya.com/")
        normalized.setdefault("User-Agent", HUYA_LIVE_USER_AGENT)
    return normalized
