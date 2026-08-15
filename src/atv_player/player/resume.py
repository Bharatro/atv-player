from urllib.parse import urlparse

from atv_player.models import HistoryRecord, PlayItem


def _basename(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.rsplit("/", 1)[-1]


def drive_relative_path(item_path: str) -> str:
    """网盘 AList 完整路径 → 资源内相对路径;/temp/<盘类型@分享ID@提取码>/ 之后的段。

    与后端 PlaybackSyncService 归一化的 drivePath 同一格式;非网盘分享路径返回 ""。
    """
    value = str(item_path or "").strip()
    marker = "/temp/"
    index = value.find(marker)
    if index < 0:
        return ""
    rest = value[index + len(marker):]
    slash = rest.find("/")
    if slash < 0:
        return ""
    return rest[slash:]


def resolve_resume_index(
    history: HistoryRecord | None,
    playlist: list[PlayItem],
    clicked_index: int,
) -> int:
    if history is None:
        return clicked_index
    # 跨端续播优先按规范网盘路径定位:坐标/集数会因资源重排、列表顺序变化而漂移,
    # "分享内相对路径"才是稳定的内容指针(与后端/安卓端同步的 drivePath 一致)。
    drive_path = str(getattr(history, "drive_path", "") or "")
    if drive_path:
        for index, item in enumerate(playlist):
            if item.path and drive_relative_path(item.path) == drive_path:
                return index
    if history.episode_url:
        target = _basename(history.episode_url)
        if target:
            for index, item in enumerate(playlist):
                if item.url and _basename(item.url) == target:
                    return index
    if 0 <= history.episode < len(playlist):
        return history.episode
    return clicked_index


def resolve_resume_index_by_drive_path(
    history: HistoryRecord | None,
    playlist: list[PlayItem],
) -> int | None:
    """按规范网盘路径在播放列表中定位条目;定位不到返回 None。"""
    drive_path = str(getattr(history, "drive_path", "") or "")
    if not drive_path:
        return None
    for index, item in enumerate(playlist):
        if item.path and drive_relative_path(item.path) == drive_path:
            return index
    return None
