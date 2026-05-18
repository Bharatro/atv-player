from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from atv_player.ui.theme import build_window_chrome_qss, current_tokens


class CustomTitleBar(QWidget):
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        allow_minimize: bool,
        allow_maximize: bool,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("customTitleBar")
        self._drag_offset: QPoint | None = None
        self.setFixedHeight(46)

        self.title_label = QLabel("", self)
        self.title_label.setObjectName("customTitleBarLabel")

        self.minimize_button = QPushButton("—", self)
        self.minimize_button.setObjectName("customTitleBarMinimizeButton")
        self.minimize_button.setVisible(allow_minimize)
        self.minimize_button.clicked.connect(self.minimize_requested.emit)

        self.maximize_button = QPushButton("□", self)
        self.maximize_button.setObjectName("customTitleBarMaximizeButton")
        self.maximize_button.setVisible(allow_maximize)
        self.maximize_button.clicked.connect(self.maximize_toggle_requested.emit)

        self.close_button = QPushButton("✕", self)
        self.close_button.setObjectName("customTitleBarCloseButton")
        self.close_button.clicked.connect(self.close_requested.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            button.setFixedSize(30, 30)
            layout.addWidget(button)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None and not window.isMaximized():
                self._drag_offset = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None and not window.isMaximized():
                window.move(event.globalPosition().toPoint() - self._drag_offset)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.maximize_button.isVisible():
            self.maximize_toggle_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class _ThemedChromeMixin:
    _window_chrome_root: QWidget
    _window_chrome_layout: QVBoxLayout
    _window_chrome_content: QWidget
    _window_chrome_content_layout: QVBoxLayout
    _title_bar: CustomTitleBar

    def _init_window_chrome(
        self,
        *,
        title: str,
        allow_minimize: bool,
        allow_maximize: bool,
    ) -> None:
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._window_chrome_root = QWidget(self)
        self._window_chrome_root.setObjectName("windowChromeRoot")
        self._window_chrome_layout = QVBoxLayout(self._window_chrome_root)
        self._window_chrome_layout.setContentsMargins(0, 0, 0, 0)
        self._window_chrome_layout.setSpacing(0)

        self._title_bar = CustomTitleBar(
            self._window_chrome_root,
            allow_minimize=allow_minimize,
            allow_maximize=allow_maximize,
        )
        self._window_chrome_layout.addWidget(self._title_bar)

        self._window_chrome_content = QWidget(self._window_chrome_root)
        self._window_chrome_content.setObjectName("windowChromeContent")
        self._window_chrome_content_layout = QVBoxLayout(self._window_chrome_content)
        self._window_chrome_content_layout.setContentsMargins(0, 0, 0, 0)
        self._window_chrome_content_layout.setSpacing(0)
        self._window_chrome_layout.addWidget(self._window_chrome_content, 1)

        self._title_bar.minimize_requested.connect(self.showMinimized)
        self._title_bar.maximize_toggle_requested.connect(self._toggle_maximized)
        self._title_bar.close_requested.connect(self.close)
        self.windowTitleChanged.connect(self._title_bar.set_title)
        self.setWindowTitle(title)
        self.refresh_window_chrome()
        self._update_window_chrome_state()

    def title_bar(self) -> CustomTitleBar:
        return self._title_bar

    def content_widget(self) -> QWidget:
        return self._window_chrome_content

    def content_layout(self) -> QVBoxLayout:
        return self._window_chrome_content_layout

    def set_title_bar_visible(self, visible: bool) -> None:
        self._title_bar.setVisible(visible)

    def refresh_window_chrome(self) -> None:
        self._window_chrome_root.setStyleSheet(build_window_chrome_qss(current_tokens()))

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._update_window_chrome_state()

    def _update_window_chrome_state(self) -> None:
        maximized = self.isMaximized() and not self.isFullScreen()
        self._window_chrome_root.setProperty("maximized", maximized)
        style = self._window_chrome_root.style()
        if style is not None:
            style.unpolish(self._window_chrome_root)
            style.polish(self._window_chrome_root)
        self._window_chrome_root.update()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self._update_window_chrome_state()


class ThemedWidgetWindowBase(QWidget, _ThemedChromeMixin):
    def __init__(
        self,
        *,
        title: str,
        allow_minimize: bool,
        allow_maximize: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_window_chrome(
            title=title,
            allow_minimize=allow_minimize,
            allow_maximize=allow_maximize,
        )
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._window_chrome_root)


class ThemedDialogBase(QDialog, _ThemedChromeMixin):
    def __init__(
        self,
        *,
        title: str,
        parent: QWidget | None = None,
        allow_maximize: bool = False,
    ) -> None:
        super().__init__(parent)
        self._init_window_chrome(
            title=title,
            allow_minimize=False,
            allow_maximize=allow_maximize,
        )
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._window_chrome_root)


class ThemedMainWindowBase(QMainWindow, _ThemedChromeMixin):
    def __init__(
        self,
        *,
        title: str,
        allow_minimize: bool = True,
        allow_maximize: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_window_chrome(
            title=title,
            allow_minimize=allow_minimize,
            allow_maximize=allow_maximize,
        )
        super().setCentralWidget(self._window_chrome_root)
