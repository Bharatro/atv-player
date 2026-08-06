from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourcePreference:
    id: str
    label: str


DANMAKU_SOURCE_PREFERENCES = (
    SourcePreference("tencent", "腾讯"),
    SourcePreference("youku", "优酷"),
    SourcePreference("bilibili", "B站"),
    SourcePreference("iqiyi", "爱奇艺"),
    SourcePreference("mgtv", "芒果"),
    SourcePreference("sohu", "搜狐"),
    SourcePreference("renren", "人人"),
    SourcePreference("dandan", "弹弹Play"),
    SourcePreference("bahamut", "巴哈姆特"),
    SourcePreference("animeko", "Animeko"),
)

METADATA_SOURCE_PREFERENCES = (
    SourcePreference("bangumi", "Bangumi"),
    SourcePreference("bilibili", "B站"),
    SourcePreference("iqiyi", "爱奇艺"),
    SourcePreference("tencent", "腾讯"),
    SourcePreference("youku", "优酷"),
    SourcePreference("sohu", "搜狐"),
    SourcePreference("local_douban", "豆瓣"),
    SourcePreference("official_douban", "豆瓣官方"),
    SourcePreference("tmdb", "TMDB"),
)

VALID_DANMAKU_PROVIDER_IDS = {item.id for item in DANMAKU_SOURCE_PREFERENCES}
VALID_METADATA_PROVIDER_IDS = {item.id for item in METADATA_SOURCE_PREFERENCES} | {
    "plugin",
    "douban",
    "remote_douban",
}
