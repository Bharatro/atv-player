from __future__ import annotations

from urllib.parse import urlparse

SHARE_TYPE_NAME_BY_ID: dict[str, str] = {
    "10": "百度",
    "9": "天翼",
    "5": "夸克",
    "7": "UC",
    "0": "阿里",
    "8": "115",
    "3": "123",
    "2": "迅雷",
    "6": "移动",
    "1": "PikPak",
    "12": "光鸭",
    "magnet": "磁力",
    "ed2k": "电驴",
    "video": "视频",
}

_SHARE_TYPE_DOMAINS: dict[str, tuple[str, ...]] = {
    "10": ("baidu.com",),
    "9": ("189.cn",),
    "5": ("quark.cn",),
    "7": ("uc.cn",),
    "0": ("alipan.com", "aliyundrive.com"),
    "8": ("115.com", "115cdn.com", "anxia.com"),
    "3": ("123pan.com", "123pan.cn", "123684.com", "123865.com", "123912.com", "123592.com"),
    "2": ("xunlei.com",),
    "6": ("139.com",),
    "1": ("mypikpak.com",),
    "12": ("guangyapan.com",),
}


def infer_share_type(value: str) -> str:
    text = str(value or "").strip()
    if not text.lower().startswith(("http://", "https://")):
        return ""
    hostname = (urlparse(text).hostname or "").lower().rstrip(".")
    for share_type, domains in _SHARE_TYPE_DOMAINS.items():
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains):
            return share_type
    return ""


def get_share_type_name(share_type: str) -> str:
    return SHARE_TYPE_NAME_BY_ID.get(str(share_type), "")
