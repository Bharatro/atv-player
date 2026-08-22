from __future__ import annotations

from urllib.parse import urlparse

__all__ = ["DRIVE_SHARE_DOMAINS", "looks_like_drive_share_link"]

DRIVE_SHARE_DOMAINS = (
    "alipan.com",
    "aliyundrive.com",
    "mypikpak.com",
    "xunlei.com",
    "123pan.com",
    "123pan.cn",
    "123684.com",
    "123865.com",
    "123912.com",
    "123592.com",
    "quark.cn",
    "139.com",
    "uc.cn",
    "115.com",
    "115cdn.com",
    "anxia.com",
    "189.cn",
    "baidu.com",
    "guangyapan.com",
)


def looks_like_drive_share_link(value: str) -> bool:
    candidate = value.strip()
    url = candidate.lower()
    if not url.startswith(("http://", "https://")):
        return False
    if url.endswith((".m3u8", ".mkv", ".mp4", ".flv")):
        return False
    hostname = (urlparse(candidate).hostname or "").lower()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in DRIVE_SHARE_DOMAINS
    )
