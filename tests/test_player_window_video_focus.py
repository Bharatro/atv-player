"""点击视频区域时控制区输入控件(输入框 / 下拉框 / 微调框)应失焦。

视频控件为 NoFocus,Qt 不会像点击控制区其他控件那样转移焦点,
PlayerWindow.eventFilter 需主动释放焦点,否则空格等快捷键会被聚焦控件吞掉。
"""

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from atv_player.controllers.player_controller import PlayerSession
from atv_player.models import PlayItem, VodItem
from atv_player.ui.player_window import PlayerWindow


class FakePlayerController:
    def report_progress(self, *args, **kwargs) -> None:
        return None

    def resolve_play_item_detail(self, session, play_item):
        return None

    def stop_playback(self, session, current_index: int) -> None:
        return None


def _session() -> PlayerSession:
    return PlayerSession(
        vod=VodItem(vod_id="s1", vod_name="Show"),
        playlist=[
            PlayItem(
                title="第2集",
                original_title="Show.S01E02.1080p.WEB-DL.x265-GRP.mkv",
                url="http://example.com/2.mkv",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )


def _make_window(qtbot) -> PlayerWindow:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(_session())
    return window


def _press_video(window: PlayerWindow, button=Qt.MouseButton.LeftButton) -> None:
    """直发 press 到视频控件而非 QTest 的 QWindow 级注入,复现真实环境的失焦缺失。"""
    app = QApplication.instance()
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        QPointF(10, 10),
        QPointF(0, 0),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )
    app.sendEvent(window.video_widget, press)


def test_video_press_releases_combo_focus(qtbot) -> None:
    window = _make_window(qtbot)
    combo = window.speed_combo
    combo.setFocus()
    assert window.focusWidget() is combo

    _press_video(window)

    assert window.focusWidget() is not combo


def test_mpv_left_click_signal_releases_focus(qtbot) -> None:
    """X11 下 mpv 子窗口拦截鼠标,点击经 left_clicked 信号转发,同样要失焦。"""
    window = _make_window(qtbot)
    spin = window.opening_spin
    spin.setFocus()
    assert window.focusWidget() is spin

    window.video_widget.left_clicked.emit()

    assert window.focusWidget() is not spin


def test_video_press_releases_spinbox_focus(qtbot) -> None:
    window = _make_window(qtbot)
    spin = window.opening_spin
    spin.setFocus()
    assert window.focusWidget() is spin

    _press_video(window)

    assert window.focusWidget() is not spin


def test_video_press_silent_without_focus(qtbot) -> None:
    window = _make_window(qtbot)
    window.speed_combo.clearFocus()
    _press_video(window)
    assert window.focusWidget() is not window.speed_combo
