from __future__ import annotations

from enum import IntFlag, auto

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QCursor, QMouseEvent
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


class _ResizeRegion(IntFlag):
    NONE = 0
    LEFT = auto()
    TOP = auto()
    RIGHT = auto()
    BOTTOM = auto()
    TOP_LEFT = TOP | LEFT
    TOP_RIGHT = TOP | RIGHT
    BOTTOM_LEFT = BOTTOM | LEFT
    BOTTOM_RIGHT = BOTTOM | RIGHT


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
        self._drag_restore_ratio = 0.5
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
        self._extra_action_buttons: list[QPushButton] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(8)
        layout.addLayout(self._actions_layout)
        self._rebuild_action_buttons()

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_extra_action_buttons(self, buttons: list[QPushButton]) -> None:
        self._extra_action_buttons = list(buttons)
        self._rebuild_action_buttons()

    def action_buttons(self) -> list[QPushButton]:
        return [
            *self._extra_action_buttons,
            self.minimize_button,
            self.maximize_button,
            self.close_button,
        ]

    def _rebuild_action_buttons(self) -> None:
        while self._actions_layout.count():
            item = self._actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self)
        for button in self.action_buttons():
            button.setFixedSize(30, 30)
            self._actions_layout.addWidget(button)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None:
                if window.isMaximized():
                    window_width = max(1, window.width())
                    self._drag_restore_ratio = event.position().x() / window_width
                    self._drag_offset = None
                else:
                    self._drag_offset = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None:
                global_pos = event.globalPosition().toPoint()
                if window.isMaximized():
                    normal_geometry = window.normalGeometry()
                    if not normal_geometry.isValid():
                        normal_geometry = window.geometry()
                    restore_x = int(normal_geometry.width() * self._drag_restore_ratio)
                    restore_y = min(self.height() // 2, normal_geometry.height())
                    target_top_left = QPoint(global_pos.x() - restore_x, global_pos.y() - restore_y)
                    window.showNormal()
                    window.move(target_top_left)
                    self._drag_offset = global_pos - target_top_left
                    event.accept()
                    return
                if self._drag_offset is not None:
                    window.move(global_pos - self._drag_offset)
                    event.accept()
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        window = self.window()
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_offset is not None
            and window is not None
            and not window.isMaximized()
            and self.maximize_button.isVisible()
            and event.globalPosition().toPoint().y() <= 0
        ):
            window.showMaximized()
            self._drag_offset = None
            event.accept()
            return
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
    _window_resizable: bool = False
    _active_resize_region: _ResizeRegion = _ResizeRegion.NONE
    _resize_start_geometry: QRect | None = None
    _resize_start_global_pos: QPoint | None = None
    _RESIZE_BORDER = 6

    def _init_window_chrome(
        self,
        *,
        title: str,
        allow_minimize: bool,
        allow_maximize: bool,
        resizable: bool = False,
    ) -> None:
        self._window_resizable = resizable
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMouseTracking(True)
        self._window_chrome_root = QWidget(self)
        self._window_chrome_root.setObjectName("windowChromeRoot")
        self._window_chrome_layout = QVBoxLayout(self._window_chrome_root)
        self._window_chrome_layout.setContentsMargins(0, 0, 0, 0)
        self._window_chrome_layout.setSpacing(0)
        self._install_resize_event_filter(self._window_chrome_root)

        self._title_bar = CustomTitleBar(
            self._window_chrome_root,
            allow_minimize=allow_minimize,
            allow_maximize=allow_maximize,
        )
        self._install_resize_event_filter_tree(self._title_bar)
        self._window_chrome_layout.addWidget(self._title_bar)

        self._window_chrome_content = QWidget(self._window_chrome_root)
        self._window_chrome_content.setObjectName("windowChromeContent")
        self._window_chrome_content_layout = QVBoxLayout(self._window_chrome_content)
        self._window_chrome_content_layout.setContentsMargins(0, 0, 0, 0)
        self._window_chrome_content_layout.setSpacing(0)
        self._install_resize_event_filter_tree(self._window_chrome_content)
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

    def is_window_resizable(self) -> bool:
        return self._window_resizable

    def is_window_resize_active(self) -> bool:
        return self._active_resize_region != _ResizeRegion.NONE

    def is_pointer_on_window_resize_edge(self, global_pos: QPoint | None = None) -> bool:
        if global_pos is None:
            global_pos = QCursor.pos()
        return self._resize_region_at(self.mapFromGlobal(global_pos)) != _ResizeRegion.NONE

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

    def _can_resize_window(self) -> bool:
        return self._window_resizable and not self.isMaximized() and not self.isFullScreen()

    def _resize_region_at(self, pos: QPoint) -> _ResizeRegion:
        if not self._can_resize_window():
            return _ResizeRegion.NONE
        rect = self.rect()
        left = pos.x() <= self._RESIZE_BORDER
        right = pos.x() >= rect.width() - self._RESIZE_BORDER
        top = pos.y() <= self._RESIZE_BORDER
        bottom = pos.y() >= rect.height() - self._RESIZE_BORDER
        region = _ResizeRegion.NONE
        if left:
            region |= _ResizeRegion.LEFT
        elif right:
            region |= _ResizeRegion.RIGHT
        if top:
            region |= _ResizeRegion.TOP
        elif bottom:
            region |= _ResizeRegion.BOTTOM
        return region

    def _install_resize_event_filter(self, widget: QWidget) -> None:
        if bool(widget.property("_resize_event_filter_installed")):
            return
        widget.installEventFilter(self)
        widget.setMouseTracking(True)
        widget.setProperty("_resize_event_filter_installed", True)

    def _install_resize_event_filter_tree(self, widget: QWidget) -> None:
        self._install_resize_event_filter(widget)
        for child in widget.findChildren(QWidget):
            self._install_resize_event_filter(child)

    def _cursor_shape_for_resize_region(self, region: _ResizeRegion) -> Qt.CursorShape:
        if region in (_ResizeRegion.TOP_LEFT, _ResizeRegion.BOTTOM_RIGHT):
            return Qt.CursorShape.SizeFDiagCursor
        if region in (_ResizeRegion.TOP_RIGHT, _ResizeRegion.BOTTOM_LEFT):
            return Qt.CursorShape.SizeBDiagCursor
        if region in (_ResizeRegion.LEFT, _ResizeRegion.RIGHT):
            return Qt.CursorShape.SizeHorCursor
        if region in (_ResizeRegion.TOP, _ResizeRegion.BOTTOM):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _update_resize_cursor(self, region: _ResizeRegion) -> None:
        if region == _ResizeRegion.NONE:
            self.unsetCursor()
            return
        self.setCursor(self._cursor_shape_for_resize_region(region))

    def _mouse_event_pos_in_self(self, event: QMouseEvent) -> QPoint:
        return self.mapFromGlobal(event.globalPosition().toPoint())

    def _handle_resize_mouse_press(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        region = self._resize_region_at(self._mouse_event_pos_in_self(event))
        if region == _ResizeRegion.NONE:
            return False
        self._active_resize_region = region
        self._resize_start_geometry = self.geometry()
        self._resize_start_global_pos = event.globalPosition().toPoint()
        self._update_resize_cursor(region)
        event.accept()
        return True

    def _perform_resize(self, global_pos: QPoint) -> None:
        if (
            self._active_resize_region == _ResizeRegion.NONE
            or self._resize_start_geometry is None
            or self._resize_start_global_pos is None
        ):
            return
        delta = global_pos - self._resize_start_global_pos
        geometry = QRect(self._resize_start_geometry)
        min_width = max(1, self.minimumWidth())
        min_height = max(1, self.minimumHeight())

        if self._active_resize_region & _ResizeRegion.LEFT:
            new_left = min(geometry.left() + delta.x(), geometry.right() - min_width + 1)
            geometry.setLeft(new_left)
        elif self._active_resize_region & _ResizeRegion.RIGHT:
            new_right = max(geometry.right() + delta.x(), geometry.left() + min_width - 1)
            geometry.setRight(new_right)

        if self._active_resize_region & _ResizeRegion.TOP:
            new_top = min(geometry.top() + delta.y(), geometry.bottom() - min_height + 1)
            geometry.setTop(new_top)
        elif self._active_resize_region & _ResizeRegion.BOTTOM:
            new_bottom = max(geometry.bottom() + delta.y(), geometry.top() + min_height - 1)
            geometry.setBottom(new_bottom)

        self.setGeometry(geometry)

    def _handle_resize_mouse_move(self, event: QMouseEvent) -> bool:
        if self._active_resize_region != _ResizeRegion.NONE and event.buttons() & Qt.MouseButton.LeftButton:
            self._perform_resize(event.globalPosition().toPoint())
            event.accept()
            return True
        self._update_resize_cursor(self._resize_region_at(self._mouse_event_pos_in_self(event)))
        return False

    def _handle_resize_mouse_release(self, event: QMouseEvent) -> bool:
        if self._active_resize_region == _ResizeRegion.NONE:
            return False
        self._active_resize_region = _ResizeRegion.NONE
        self._resize_start_geometry = None
        self._resize_start_global_pos = None
        self._update_resize_cursor(self._resize_region_at(self._mouse_event_pos_in_self(event)))
        event.accept()
        return True

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
            if not self._can_resize_window():
                self._active_resize_region = _ResizeRegion.NONE
                self._resize_start_geometry = None
                self._resize_start_global_pos = None
                self.unsetCursor()

    def childEvent(self, event) -> None:
        super().childEvent(event)
        child = event.child()
        if isinstance(child, QWidget):
            self._install_resize_event_filter_tree(child)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.ChildAdded:
            child_getter = getattr(event, "child", None)
            child = child_getter() if callable(child_getter) else None
            if isinstance(child, QWidget):
                self._install_resize_event_filter_tree(child)
        if isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress and self._handle_resize_mouse_press(event):
                return True
            if event.type() == QEvent.Type.MouseMove and self._handle_resize_mouse_move(event):
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._handle_resize_mouse_release(event):
                return True
        elif event.type() == QEvent.Type.Leave and self._active_resize_region == _ResizeRegion.NONE:
            self.unsetCursor()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._handle_resize_mouse_press(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._handle_resize_mouse_move(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._handle_resize_mouse_release(event):
            return
        super().mouseReleaseEvent(event)


class ThemedWidgetWindowBase(_ThemedChromeMixin, QWidget):
    def __init__(
        self,
        *,
        title: str,
        allow_minimize: bool,
        allow_maximize: bool,
        resizable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_window_chrome(
            title=title,
            allow_minimize=allow_minimize,
            allow_maximize=allow_maximize,
            resizable=resizable,
        )
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._window_chrome_root)


class ThemedDialogBase(_ThemedChromeMixin, QDialog):
    def __init__(
        self,
        *,
        title: str,
        parent: QWidget | None = None,
        allow_maximize: bool = False,
        resizable: bool = True,
    ) -> None:
        super().__init__(parent)
        self._init_window_chrome(
            title=title,
            allow_minimize=False,
            allow_maximize=allow_maximize,
            resizable=resizable,
        )
        self._window_chrome_content_layout.setContentsMargins(12, 12, 12, 12)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._window_chrome_root)


class ThemedMainWindowBase(_ThemedChromeMixin, QMainWindow):
    def __init__(
        self,
        *,
        title: str,
        allow_minimize: bool = True,
        allow_maximize: bool = True,
        resizable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_window_chrome(
            title=title,
            allow_minimize=allow_minimize,
            allow_maximize=allow_maximize,
            resizable=resizable,
        )
        super().setCentralWidget(self._window_chrome_root)
