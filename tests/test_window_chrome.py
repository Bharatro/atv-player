from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from atv_player.ui.window_chrome import (
    ThemedDialogBase,
    ThemedWidgetWindowBase,
)


class DemoWindow(ThemedWidgetWindowBase):
    def __init__(self) -> None:
        super().__init__(title="Demo Window", allow_minimize=True, allow_maximize=True, resizable=True)
        self.content_layout().addWidget(QLabel("body", self.content_widget()))


class DemoDialog(ThemedDialogBase):
    def __init__(self) -> None:
        super().__init__(title="Demo Dialog")
        self.content_layout().addWidget(QLabel("body", self.content_widget()))


class FixedSizeDemoDialog(ThemedDialogBase):
    def __init__(self) -> None:
        super().__init__(title="Fixed Demo Dialog", resizable=False)
        self.content_layout().addWidget(QLabel("body", self.content_widget()))


class ActionWindow(ThemedWidgetWindowBase):
    def __init__(self) -> None:
        super().__init__(title="Action Window", allow_minimize=True, allow_maximize=True, resizable=True)
        self.return_button = QPushButton("返回", self.title_bar())
        self.title_bar().set_extra_action_buttons([self.return_button])


def test_themed_widget_window_exposes_custom_title_bar_and_frameless_flag(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)

    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert window.title_bar().objectName() == "customTitleBar"
    assert window.title_bar().title_label.text() == "Demo Window"


def test_themed_dialog_hides_maximize_button_by_default(qtbot) -> None:
    dialog = DemoDialog()
    qtbot.addWidget(dialog)

    assert dialog.title_bar().maximize_button.isHidden() is True
    assert dialog.title_bar().minimize_button.isHidden() is True


def test_themed_dialog_applies_default_content_padding(qtbot) -> None:
    dialog = DemoDialog()
    qtbot.addWidget(dialog)

    margins = dialog.content_layout().contentsMargins()

    assert margins.left() > 0
    assert margins.top() > 0
    assert margins.right() > 0
    assert margins.bottom() > 0


def test_themed_widget_window_can_enable_resize_support(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)

    assert window.is_window_resizable() is True


def test_themed_dialog_defaults_to_resize_support(qtbot) -> None:
    dialog = DemoDialog()
    qtbot.addWidget(dialog)

    assert dialog.is_window_resizable() is True


def test_themed_dialog_can_disable_resize_support_explicitly(qtbot) -> None:
    dialog = FixedSizeDemoDialog()
    qtbot.addWidget(dialog)

    assert dialog.is_window_resizable() is False


def test_themed_widget_window_reports_resize_region_near_edges(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(640, 480)
    window.show()
    qtbot.wait(50)

    assert window._resize_region_at(window.rect().topLeft()).name == "TOP_LEFT"
    assert window._resize_region_at(window.rect().center()).name == "NONE"


def test_themed_dialog_dragging_right_edge_resizes_window(qtbot) -> None:
    dialog = DemoDialog()
    qtbot.addWidget(dialog)
    dialog.resize(400, 300)
    dialog.show()
    qtbot.wait(50)

    start_rect = dialog.geometry()
    press_global = dialog.mapToGlobal(QPoint(dialog.width() - 2, dialog.height() // 2))
    press_local = dialog._window_chrome_root.mapFromGlobal(press_global)
    QApplication.sendEvent(
        dialog._window_chrome_root,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            press_local,
            press_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    move_global = press_global + QPoint(40, 0)
    move_local = dialog._window_chrome_root.mapFromGlobal(move_global)
    QApplication.sendEvent(
        dialog._window_chrome_root,
        QMouseEvent(
            QEvent.Type.MouseMove,
            move_local,
            move_global,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.sendEvent(
        dialog._window_chrome_root,
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            move_local,
            move_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    assert dialog.geometry().width() > start_rect.width()


def test_themed_widget_window_dragging_right_edge_through_descendant_resizes_window(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(400, 300)

    edge_button = QPushButton("edge", window.content_widget())
    window.show()
    qtbot.wait(50)
    edge_button.setGeometry(window.content_widget().width() - 40, 60, 40, 120)

    start_rect = window.geometry()
    press_global = edge_button.mapToGlobal(QPoint(edge_button.width() - 2, edge_button.rect().center().y()))
    press_local = edge_button.mapFromGlobal(press_global)
    QApplication.sendEvent(
        edge_button,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            press_local,
            press_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    move_global = press_global + QPoint(40, 0)
    move_local = edge_button.mapFromGlobal(move_global)
    QApplication.sendEvent(
        edge_button,
        QMouseEvent(
            QEvent.Type.MouseMove,
            move_local,
            move_global,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.sendEvent(
        edge_button,
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            move_local,
            move_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    assert window.geometry().width() > start_rect.width()


def test_themed_widget_window_allows_descendant_button_clicks_away_from_resize_border(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(400, 300)

    center_button = QPushButton("center", window.content_widget())
    center_button.setGeometry(120, 100, 120, 48)
    clicks: list[bool] = []
    center_button.clicked.connect(lambda checked=False: clicks.append(checked))

    window.show()
    qtbot.wait(50)

    qtbot.mouseClick(center_button, Qt.MouseButton.LeftButton)

    assert clicks == [False]


def test_themed_widget_window_missed_resize_release_does_not_break_next_button_click(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(400, 300)

    edge_button = QPushButton("edge", window.content_widget())
    center_button = QPushButton("center", window.content_widget())
    clicks: list[bool] = []
    center_button.clicked.connect(lambda checked=False: clicks.append(checked))

    window.show()
    qtbot.wait(50)
    edge_button.setGeometry(window.content_widget().width() - 40, 60, 40, 120)
    center_button.setGeometry(120, 100, 120, 48)

    press_global = edge_button.mapToGlobal(QPoint(edge_button.width() - 2, edge_button.rect().center().y()))
    press_local = edge_button.mapFromGlobal(press_global)
    QApplication.sendEvent(
        edge_button,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            press_local,
            press_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    move_global = press_global + QPoint(40, 0)
    move_local = edge_button.mapFromGlobal(move_global)
    QApplication.sendEvent(
        edge_button,
        QMouseEvent(
            QEvent.Type.MouseMove,
            move_local,
            move_global,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    qtbot.mouseClick(center_button, Qt.MouseButton.LeftButton)

    assert clicks == [False]


def test_themed_widget_window_ignores_resize_hit_testing_for_unrelated_watched_widget(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(400, 300)
    window.show()
    qtbot.wait(50)

    other_host = QWidget()
    qtbot.addWidget(other_host)
    other_button = QPushButton("other", other_host)
    other_button.setGeometry(0, 0, 100, 40)
    other_host.show()
    qtbot.wait(50)

    global_pos = window.mapToGlobal(QPoint(window.width() - 2, window.height() // 2))
    local_pos = other_button.mapFromGlobal(global_pos)
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        local_pos,
        global_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    handled = window.eventFilter(other_button, event)

    assert handled is False


def test_title_bar_visibility_toggle_hides_chrome_without_hiding_content(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.show()

    window.set_title_bar_visible(False)

    assert window.title_bar().isHidden() is True
    assert window.content_widget().isVisible() is True


def test_double_clicking_title_label_toggles_maximized_state(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(640, 480)
    window.show()
    qtbot.wait(50)

    label = window.title_bar().title_label
    local_pos = label.rect().center()
    global_pos = label.mapToGlobal(local_pos)
    double_click_event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        local_pos,
        global_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        local_pos,
        global_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    QApplication.sendEvent(label, double_click_event)
    QApplication.sendEvent(label, release_event)

    assert window.isMaximized() is True

    QApplication.sendEvent(label, double_click_event)
    QApplication.sendEvent(label, release_event)

    assert window.isMaximized() is False


def test_dragging_title_bar_to_top_edge_requests_maximize(qtbot, monkeypatch) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(640, 480)
    window.show()
    qtbot.wait(50)

    title_bar = window.title_bar()
    press_local = title_bar.rect().center()
    press_global = title_bar.mapToGlobal(press_local)
    release_global = QPoint(press_global.x() + 30, 0)
    release_local = title_bar.mapFromGlobal(release_global)
    calls: list[str] = []
    state = {"maximized": False}

    monkeypatch.setattr(window, "isMaximized", lambda: state["maximized"])

    def fake_show_maximized() -> None:
        calls.append("showMaximized")
        state["maximized"] = True

    monkeypatch.setattr(window, "showMaximized", fake_show_maximized)

    QApplication.sendEvent(
        title_bar,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            press_local,
            press_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.sendEvent(
        title_bar,
        QMouseEvent(
            QEvent.Type.MouseMove,
            release_local,
            release_global,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.sendEvent(
        title_bar,
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            release_local,
            release_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    assert calls == ["showMaximized"]


def test_dragging_maximized_title_bar_down_restores_window(qtbot, monkeypatch) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(640, 480)
    window.show()
    qtbot.wait(50)

    title_bar = window.title_bar()
    press_local = title_bar.rect().center()
    press_global = title_bar.mapToGlobal(press_local)
    move_global = press_global + QPoint(60, 80)
    move_local = title_bar.mapFromGlobal(move_global)
    calls: list[str] = []
    state = {"maximized": True}
    moved_positions: list[QPoint] = []
    normal_geometry = QRect(160, 120, 640, 480)

    monkeypatch.setattr(window, "isMaximized", lambda: state["maximized"])
    monkeypatch.setattr(window, "normalGeometry", lambda: QRect(normal_geometry))

    def fake_show_normal() -> None:
        calls.append("showNormal")
        state["maximized"] = False

    monkeypatch.setattr(window, "showNormal", fake_show_normal)
    monkeypatch.setattr(window, "move", lambda pos: moved_positions.append(QPoint(pos)))

    QApplication.sendEvent(
        title_bar,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            press_local,
            press_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.sendEvent(
        title_bar,
        QMouseEvent(
            QEvent.Type.MouseMove,
            move_local,
            move_global,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    assert calls == ["showNormal"]
    assert moved_positions


def test_themed_widget_window_title_bar_can_insert_extra_action_buttons(qtbot) -> None:
    window = ActionWindow()
    qtbot.addWidget(window)

    buttons = [button.text() for button in window.title_bar().action_buttons()]

    assert buttons == ["返回", "—", "□", "✕"]
