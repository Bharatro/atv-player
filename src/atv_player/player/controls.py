"""播放控制层。

PlayerControls 是所有 mpv 写控制操作的统一入口(非可视 mediator)。
播放控件物理留在 PlayerWindow,避免布局 / 全屏 / 主题 / 宽度自适应大面积回归。

演进:
- Phase 1(当前):纯 mpv 操作代理,PlayerWindow 的写控制调用经此转发,行为零变化。
- Phase 2:快捷键注册表(_register_shortcuts + 窗口级键)迁入 register_shortcuts。
- Phase 4:字幕延迟 / 音频延迟 / 画面调节(亮度/对比度/饱和度/色调/伽马)的
  setter、右键菜单 builder、延迟快捷键落在此(P0)。

迁移约束(新增/迁入功能时务必遵守):
- 字幕 position / scale / ass_override 不迁入本类——它们被弹幕复用 mpv 字幕槽
  (见 PlayerWindow._restore_*_after_danmaku 系列)。
- P0 的 sub-delay / audio-delay / 画面 EQ 是纯时间 / 像素属性,与字幕槽无关,可安全在此。
- 不在本类加线程逻辑:MpvWidget setter 已自带 widget 线程卫兵,UI 线程直调即可。

持久化扩展点(本次不做):若将来要把 P0 默认值存库,在 AppConfig(models.py:24,
slots=True)加字段,并改 storage.py 六处(CREATE/ALTER/SELECT/构造/UPDATE/绑定)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

if TYPE_CHECKING:
    from atv_player.models import AppConfig
    from atv_player.player.mpv_widget import MpvWidget


class PlayerControls(QObject):
    """mpv 写控制的统一入口。读查询 / 加载 / 轨道仍直接用 MpvWidget。"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config: AppConfig | None = None

    def bind(self, *, config: AppConfig | None) -> None:
        self._config = config

    @property
    def _video(self) -> MpvWidget | None:
        # 委托给 owner(PlayerWindow).video,随其重新赋值(含测试注入 mock)同步。
        owner = self.parent()
        return getattr(owner, "video", None)

    # ── 纯播放控制(mpv I/O 代理);UI 副作用仍由 PlayerWindow 处理 ──

    def pause(self) -> None:
        self._video.pause()

    def resume(self) -> None:
        self._video.resume()

    def seek(self, seconds: int) -> None:
        self._video.seek(seconds)

    def seek_relative(self, seconds: int) -> None:
        self._video.seek_relative(seconds)

    def set_volume(self, value: int) -> None:
        self._video.set_volume(value)

    def set_speed(self, speed: float) -> None:
        self._video.set_speed(speed)

    def toggle_mute(self) -> None:
        self._video.toggle_mute()

    def set_muted(self, muted: bool) -> None:
        if hasattr(self._video, "set_muted"):
            self._video.set_muted(muted)

    # ── P0:字幕/音频延迟与画面调节(纯 mpv 属性写,值由 PlayerWindow 会话内字段跟踪)──

    def set_subtitle_delay(self, seconds: float) -> None:
        self._video.set_subtitle_delay(seconds)

    def set_audio_delay(self, seconds: float) -> None:
        self._video.set_audio_delay(seconds)

    def set_picture(self, prop: str, value: int) -> None:
        getattr(self._video, "set_" + prop)(value)
