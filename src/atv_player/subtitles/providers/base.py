from __future__ import annotations

from typing import Protocol

from atv_player.subtitles.models import (
    SubtitleContent,
    SubtitleQuery,
    SubtitleSearchItem,
)


class SubtitleProvider(Protocol):
    """字幕站接口。

    实现约定：

    - ``search`` 只负责取回候选并做最基本的归一，排序交给 SubtitleSearchService。
    - ``search`` / ``download`` 失败时抛 SubtitleProviderError 的子类，
      由 service 收敛成"该站失败"，不影响其他站。
    - ``available`` 为 False 时 service 会静默跳过（通常是需要 token 但没配）。
    """

    provider_id: str
    label: str
    requires_token: bool
    notice: str

    def available(self) -> bool: ...

    def search(self, query: SubtitleQuery) -> list[SubtitleSearchItem]: ...

    def download(self, item: SubtitleSearchItem) -> SubtitleContent: ...
