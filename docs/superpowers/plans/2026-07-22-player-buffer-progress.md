# 播放器缓存进度显示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在播放器进度条上以一段浅色显示当前播放位置之后已缓冲的时长（mpv `demuxer-cache-duration`），形成「已播放 / 已缓存 / 未缓存」三段，无文字。

**Architecture:** 复用现有 `progress_timer` → `_sync_progress_slider` 轮询通道按需读取 mpv 的 `demuxer-cache-duration`，交给 `ClickableSlider` 的新 `_buffer_value` 状态，由其自定义 `paintEvent` 在 accent 段之前绘制缓存段。新增一个主题 token `player_buffer` 提供颜色。

**Tech Stack:** Python 3.12, PySide6 (QtWidgets/QtGui/QtCore), python-mpv, pytest + pytest-qt (qtbot)。

## Global Constraints

- 数据来源仅为 mpv 的 `demuxer-cache-duration` 属性；不接入 m3u8 代理、不改配置/持久化、不加文字标签、不改轮询频率。
- 读取缓存时长须复刻现有 `duration_seconds()` 的线程安全模式（`_on_widget_thread()` 守卫 + `_player_property` + `_seconds_property_value`），`None`/异常/负值归一化为 0。
- 颜色用新增的可主题化 token `player_buffer`，不复用 `border_subtle`（避免与禁用态轨道撞色）。
- 对缺少 `demuxer_cache_duration_seconds` 的视频控件必须优雅降级（缓存按 0 处理，不抛异常）。
- `player_tokens_for` 恒返回 `PLAYER_IMMERSIVE_TOKENS`，故绘制实际只用该实例的 `player_buffer`；但 `player_buffer: str` 是必填字段，`LIGHT_TOKENS`、`DARK_TOKENS`、`PLAYER_IMMERSIVE_TOKENS` 三个实例都必须提供。

## File Structure

- **Modify** `src/atv_player/ui/theme.py` — `ThemeTokens` 数据类 + 3 个实例新增 `player_buffer` 字段。
- **Modify** `src/atv_player/player/mpv_widget.py` — `MpvWidget` 新增 `demuxer_cache_duration_seconds()`。
- **Modify** `src/atv_player/ui/player_window.py` — `ClickableSlider` 新增 `_buffer_value`/`set_buffer_value()` + `paintEvent` 绘制缓存段；`_sync_progress_slider` 喂数据；项切换重置。
- **Modify** `tests/test_theme.py`、`tests/test_mpv_widget.py`、`tests/test_player_window_ui.py` — 各任务对应测试。

---

### Task 1: 新增 `player_buffer` 主题 token

**Files:**
- Modify: `src/atv_player/ui/theme.py:173`（`ThemeTokens` 数据类）、`src/atv_player/ui/theme.py:191`/`238`/`285`（三个实例）
- Test: `tests/test_theme.py`

**Interfaces:**
- Produces: `ThemeTokens.player_buffer: str`（hex 颜色），供 Task 3 的 `paintEvent` 通过 `tokens.player_buffer` 读取。

- [ ] **Step 1: Write the failing test**

在 `tests/test_theme.py` 末尾追加：

```python
def test_theme_tokens_expose_player_buffer() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")

    assert manager.tokens_for("light").player_buffer.startswith("#")
    assert manager.tokens_for("dark").player_buffer.startswith("#")
    assert manager.player_tokens_for("dark").player_buffer.startswith("#")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py::test_theme_tokens_expose_player_buffer -v`
Expected: FAIL — `AttributeError: 'ThemeTokens' object has no attribute 'player_buffer'`

- [ ] **Step 3: Write minimal implementation**

在 `src/atv_player/ui/theme.py` 的 `ThemeTokens` 数据类中，紧接 `player_button_border: str`（约 173 行）之后新增一行：

```python
    player_button_border: str
    player_buffer: str
    player_button_icon: str
```

在三个实例中，紧接各自的 `player_button_border="...",` 之后新增 `player_buffer`：

`LIGHT_TOKENS`（约 220 行后）：

```python
    player_button_border="#536078",
    player_buffer="#bcb2a3",
    player_button_icon="#f5f7fb",
```

`DARK_TOKENS`（约 267 行后）：

```python
    player_button_border="#536078",
    player_buffer="#6e7a90",
    player_button_icon="#f5f7fb",
```

`PLAYER_IMMERSIVE_TOKENS`（约 314 行后）：

```python
    player_button_border="#536078",
    player_buffer="#6e7a90",
    player_button_icon="#f5f7fb",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`
Expected: PASS（含新增测试与既有主题测试全部通过）

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/theme.py tests/test_theme.py
git commit -m "feat: add player_buffer theme token"
```

---

### Task 2: `MpvWidget.demuxer_cache_duration_seconds()`

**Files:**
- Modify: `src/atv_player/player/mpv_widget.py:1315`（紧接 `duration_seconds()` 之后）
- Test: `tests/test_mpv_widget.py`

**Interfaces:**
- Consumes: `MpvWidget._on_widget_thread()`、`MpvWidget._run_on_widget_thread()`、`MpvWidget._player_property(name, default)`、`MpvWidget._seconds_property_value(value)`（均已存在）。
- Produces: `MpvWidget.demuxer_cache_duration_seconds() -> int`，供 Task 4 的 `_sync_progress_slider` 通过 `self.video.demuxer_cache_duration_seconds()` 读取。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_mpv_widget.py` 追加（仿照既有 `test_mpv_widget_duration_prefers_live_mpv_property_when_attribute_is_zero`）：

```python
def test_mpv_widget_demuxer_cache_duration_reads_live_property(qtbot, monkeypatch) -> None:
    widget = MpvWidget()
    qtbot.addWidget(widget)
    monkeypatch.setattr("atv_player.player.mpv_widget.sys.platform", "win32")

    class FakePlayer:
        def __getitem__(self, key: str) -> object:
            if key == "demuxer-cache-duration":
                return 42.7
            raise KeyError(key)

    widget._player = FakePlayer()

    assert widget.demuxer_cache_duration_seconds() == 42


def test_mpv_widget_demuxer_cache_duration_returns_zero_when_missing(qtbot, monkeypatch) -> None:
    widget = MpvWidget()
    qtbot.addWidget(widget)
    monkeypatch.setattr("atv_player.player.mpv_widget.sys.platform", "win32")

    class FakePlayer:
        def __getitem__(self, key: str) -> object:
            raise KeyError(key)

    widget._player = FakePlayer()

    assert widget.demuxer_cache_duration_seconds() == 0


def test_mpv_widget_demuxer_cache_duration_returns_zero_without_player(qtbot) -> None:
    widget = MpvWidget()
    qtbot.addWidget(widget)

    widget._player = None

    assert widget.demuxer_cache_duration_seconds() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mpv_widget.py -k demuxer_cache_duration -v`
Expected: FAIL — `AttributeError: 'MpvWidget' object has no attribute 'demuxer_cache_duration_seconds'`

- [ ] **Step 3: Write minimal implementation**

在 `src/atv_player/player/mpv_widget.py` 的 `duration_seconds()` 方法之后（约 1315 行、`_subtitle_language_label` 之前）新增：

```python
    def demuxer_cache_duration_seconds(self) -> int:
        if not self._on_widget_thread():
            return int(self._run_on_widget_thread(self.demuxer_cache_duration_seconds) or 0)
        if self._player is None:
            return 0
        return self._seconds_property_value(self._player_property("demuxer-cache-duration", None))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mpv_widget.py -k demuxer_cache_duration -v`
Expected: PASS（3 条全部通过）

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/player/mpv_widget.py tests/test_mpv_widget.py
git commit -m "feat: expose mpv demuxer-cache-duration"
```

---

### Task 3: `ClickableSlider` 缓存段状态与绘制

**Files:**
- Modify: `src/atv_player/ui/player_window.py:278-319`（`ClickableSlider.__init__` 与 `paintEvent`）
- Test: `tests/test_player_window_ui.py`

**Interfaces:**
- Consumes: Task 1 的 `tokens.player_buffer`；`QColor`（已导入）。
- Produces: `ClickableSlider._buffer_value: int`（初值 0）、`ClickableSlider.set_buffer_value(value: int)`，供 Task 4 调用与测试读取。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_player_window_ui.py` 顶部导入处，把 `from atv_player.ui.player_window import PlayerWindow` 改为：

```python
from atv_player.ui.player_window import ClickableSlider, PlayerWindow
```

在文件末尾追加：

```python
def test_clickable_slider_buffer_value_clamps_to_range(qtbot) -> None:
    slider = ClickableSlider(Qt.Orientation.Horizontal)
    qtbot.addWidget(slider)
    slider.setMinimum(0)
    slider.setMaximum(100)
    slider.setValue(30)

    slider.set_buffer_value(70)
    assert slider._buffer_value == 70

    slider.set_buffer_value(250)
    assert slider._buffer_value == 100

    slider.set_buffer_value(-5)
    assert slider._buffer_value == 0


def test_clickable_slider_paints_without_error_with_buffer(qtbot) -> None:
    slider = ClickableSlider(Qt.Orientation.Horizontal)
    qtbot.addWidget(slider)
    slider.setMinimum(0)
    slider.setMaximum(100)
    slider.setValue(30)
    slider.set_buffer_value(70)
    slider.resize(200, 24)

    pixmap = slider.grab()

    assert not pixmap.isNull()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_player_window_ui.py -k clickable_slider -v`
Expected: FAIL — `AttributeError: 'ClickableSlider' object has no attribute 'set_buffer_value'`

- [ ] **Step 3: Write minimal implementation**

在 `src/atv_player/ui/player_window.py` 的 `ClickableSlider.__init__` 中，紧接 `self._hover_tooltip_formatter: Callable[[int], str] | None = None`（约 280 行）之后新增：

```python
        self._hover_tooltip_formatter: Callable[[int], str] | None = None
        self._buffer_value: int = 0
```

在 `set_hover_tooltip_formatter` 方法之前（约 352 行）新增 setter：

```python
    def set_buffer_value(self, value: int) -> None:
        clamped = max(self.minimum(), min(int(value), self.maximum()))
        if clamped == self._buffer_value:
            return
        self._buffer_value = clamped
        self.update()

    def set_hover_tooltip_formatter(self, formatter: Callable[[int], str] | None) -> None:
```

在 `paintEvent` 中，整条轨道绘制（`drawRoundedRect(0, track_top, self.width(), ...)`，约 303 行）之后、accent 已播放段绘制（`if self.isEnabled() and handle_center_x > handle_diameter / 2:`，约 305 行）之前，插入缓存段绘制：

```python
        painter.setBrush(QColor(track_color))
        painter.drawRoundedRect(0, track_top, self.width(), track_height, track_height / 2, track_height / 2)

        if self.isEnabled() and self._buffer_value > self.value():
            buffer_progress = (self._buffer_value - self.minimum()) / value_range
            buffer_end_x = handle_diameter / 2 + buffer_progress * available_width
            painter.setBrush(QColor(tokens.player_buffer))
            painter.drawRoundedRect(0, track_top, buffer_end_x, track_height, track_height / 2, track_height / 2)

        if self.isEnabled() and handle_center_x > handle_diameter / 2:
            painter.setBrush(QColor(tokens.accent))
            painter.drawRoundedRect(0, track_top, handle_center_x, track_height, track_height / 2, track_height / 2)
```

> 说明：缓存段从 0 画到 `buffer_end_x`，随后 accent 段从 0 画到 `handle_center_x` 覆盖其上，故可见缓存区为 `[当前位置, 缓存终点]`，位于手柄右侧；与设计稿一致。

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_player_window_ui.py -k clickable_slider -v`
Expected: PASS（2 条全部通过）

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: render buffer segment on player slider"
```

---

### Task 4: `_sync_progress_slider` 桥接 + 项切换重置

**Files:**
- Modify: `src/atv_player/ui/player_window.py:9247-9250`（`_sync_progress_slider` 末尾）、`src/atv_player/ui/player_window.py:3041`（项切换重置）
- Test: `tests/test_player_window_ui.py`

**Interfaces:**
- Consumes: Task 2 的 `self.video.demuxer_cache_duration_seconds()`、Task 3 的 `self.progress.set_buffer_value(value)`。
- Produces: 进度条在每次轮询与项切换时正确反映缓存段。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_player_window_ui.py` 末尾追加（`make_player_session`、`VodItem`、`RecordingVideo`、`FakePlayerController` 均已在文件中定义/导入）：

```python
def test_sync_progress_slider_sets_buffer_value_from_cache(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.progress_timer.stop()
    session = make_player_session(start_index=0)
    session.vod = VodItem(vod_id="movie-1", vod_name="Movie")
    window.open_session(session)
    window.video = type(
        "Video",
        (),
        {
            "position_seconds": lambda _self: 30,
            "duration_seconds": lambda _self: 120,
            "demuxer_cache_duration_seconds": lambda _self: 40,
        },
    )()

    window._sync_progress_slider()

    assert window.progress.value() == 30
    assert window.progress._buffer_value == 70


def test_sync_progress_slider_clamps_buffer_to_duration(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.progress_timer.stop()
    session = make_player_session(start_index=0)
    session.vod = VodItem(vod_id="movie-1", vod_name="Movie")
    window.open_session(session)
    window.video = type(
        "Video",
        (),
        {
            "position_seconds": lambda _self: 100,
            "duration_seconds": lambda _self: 120,
            "demuxer_cache_duration_seconds": lambda _self: 200,
        },
    )()

    window._sync_progress_slider()

    assert window.progress._buffer_value == 120


def test_sync_progress_slider_handles_missing_cache_method(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.progress_timer.stop()
    session = make_player_session(start_index=0)
    session.vod = VodItem(vod_id="movie-1", vod_name="Movie")
    window.open_session(session)
    window.video = RecordingVideo()  # 没有 demuxer_cache_duration_seconds

    window._sync_progress_slider()

    assert window.progress._buffer_value == window.progress.value()


def test_open_session_resets_buffer_value(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.progress_timer.stop()
    window.progress.setMaximum(100)
    window.progress.set_buffer_value(90)
    session = make_player_session(start_index=0)
    session.vod = VodItem(vod_id="movie-1", vod_name="Movie")

    window.open_session(session)

    assert window.progress._buffer_value == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_player_window_ui.py -k "sync_progress_slider or open_session_resets_buffer" -v`
Expected: FAIL — 前三条 `assert ... == 70/120/value()` 失败（`_buffer_value` 仍为 0 或旧值）；第四条 `assert 0` 失败（未重置）。

- [ ] **Step 3: Write minimal implementation**

在 `src/atv_player/ui/player_window.py` 的 `_sync_progress_slider` 末尾，把：

```python
        self.progress.setMaximum(max(effective_duration, 0))
        self.progress.setValue(max(min(position, self.progress.maximum()), 0))
        self.current_time_label.setText(self._format_time(position))
        self.duration_label.setText(self._format_time(effective_duration))
```

改为：

```python
        self.progress.setMaximum(max(effective_duration, 0))
        self.progress.setValue(max(min(position, self.progress.maximum()), 0))
        cache_duration = 0
        if hasattr(self.video, "demuxer_cache_duration_seconds"):
            try:
                cache_duration = int(self.video.demuxer_cache_duration_seconds() or 0)
            except Exception:
                cache_duration = 0
        buffer_end = min(int(position) + cache_duration, max(effective_duration, 0))
        self.progress.set_buffer_value(buffer_end)
        self.current_time_label.setText(self._format_time(position))
        self.duration_label.setText(self._format_time(effective_duration))
```

在项切换重置处（约 3041 行 `self.progress.setValue(0)`）紧接其后新增重置缓存：

```python
        self.progress.setValue(0)
        self.progress.set_buffer_value(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_player_window_ui.py -k "sync_progress_slider or open_session_resets_buffer" -v`
Expected: PASS（4 条全部通过）

- [ ] **Step 5: Run the full affected suite**

Run: `pytest tests/test_theme.py tests/test_mpv_widget.py tests/test_player_window_ui.py -v`
Expected: PASS（无回归）

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: wire demuxer cache duration into player slider"
```

---

## 收尾人工验证

实现并全部测试通过后，运行播放器播放一段网络视频，目视确认：

- 进度条手柄右侧出现浅色缓存段，随缓冲增长、随 seek 缩短。
- 本地文件缓存段自然延伸到末端，不报错。
- 直播/无 duration 场景不绘制缓存段。
- 切换剧集后缓存段从空开始，不残留。
- 切换主题时缓存段颜色正确变化。
