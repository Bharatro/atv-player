from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

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


def test_themed_dialog_keeps_resize_support_disabled(qtbot) -> None:
    dialog = DemoDialog()
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


def test_title_bar_visibility_toggle_hides_chrome_without_hiding_content(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.show()

    window.set_title_bar_visible(False)

    assert window.title_bar().isHidden() is True
    assert window.content_widget().isVisible() is True
