# 播放器弹幕单集链接下载实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在播放窗口的弹幕源对话框中粘贴已支持视频平台的单集播放页 URL，后台下载并立即加载该集弹幕。

**Architecture:** `DanmakuService` 提供遵守来源禁用设置的 URL-provider 识别接口；各播放会话的弹幕控制器提供统一的 `download_danmaku_from_url()` 方法并原子更新 `PlayItem`。`PlayerWindow` 只负责输入校验、后台任务调度、状态展示和成功后的弹幕重载，缓存、清洗和 XML 构建仍走现有链路。

**Tech Stack:** Python 3.12、PySide6、httpx、pytest、pytest-qt

---

## 文件结构

- 修改 `src/atv_player/danmaku/service.py`：识别支持指定 URL 的已启用 provider。
- 修改 `src/atv_player/danmaku/generic.py`：共享 URL 规范化函数和通用控制器直链下载方法。
- 修改 `src/atv_player/danmaku/direct_parse.py`：让直解析播放会话实现相同控制器接口。
- 修改 `src/atv_player/plugins/controller.py`：让 Spider 播放会话实现相同控制器接口并保留其偏好缓存行为。
- 修改 `src/atv_player/ui/player_window.py`：增加单集链接输入、下载动作、任务状态和立即重载。
- 修改 `docs/help.md`：记录单集链接下载入口。
- 修改 `tests/test_danmaku_service.py`、`tests/test_generic_danmaku_controller.py`、`tests/test_direct_parse_danmaku.py`、`tests/test_spider_plugin_controller.py`、`tests/test_player_window_ui.py`：覆盖服务、控制器和 UI 行为。

### Task 1: 服务层按 URL 识别已启用 provider

**Files:**
- Modify: `src/atv_player/danmaku/service.py:350`
- Test: `tests/test_danmaku_service.py:1555`

- [ ] **Step 1: 写 provider 匹配的失败测试**

在 `tests/test_danmaku_service.py` 的 resolve 测试附近加入：

```python
def test_provider_key_for_url_returns_first_enabled_supporting_provider() -> None:
    tencent = FakeProvider("tencent", [], [])
    youku = FakeProvider("youku", [], [])
    service = DanmakuService(
        {"tencent": tencent, "youku": youku},
        provider_order=["tencent", "youku"],
    )

    assert service.provider_key_for_url("https://video.youku/item") == "youku"


def test_provider_key_for_url_rejects_dynamically_disabled_provider() -> None:
    disabled = ["youku"]
    service = DanmakuService(
        {"youku": FakeProvider("youku", [], [])},
        provider_order=["youku"],
        disabled_provider_ids_loader=lambda: disabled,
    )

    with pytest.raises(ProviderNotSupportedError, match="不支持的弹幕来源"):
        service.provider_key_for_url("https://video.youku/item")


def test_provider_key_for_url_rejects_unknown_url() -> None:
    service = DanmakuService({}, provider_order=[])

    with pytest.raises(ProviderNotSupportedError, match="不支持的弹幕来源"):
        service.provider_key_for_url("https://unknown.example/video/1")
```

- [ ] **Step 2: 运行测试并确认因接口缺失失败**

Run: `uv run pytest tests/test_danmaku_service.py -k 'provider_key_for_url' -v`

Expected: FAIL，`DanmakuService` 没有 `provider_key_for_url`。

- [ ] **Step 3: 实现最小 provider 匹配接口**

在 `DanmakuService` 的 provider 顺序辅助方法附近加入：

```python
def provider_key_for_url(self, page_url: str) -> str:
    for key in self._provider_order:
        if not self._provider_enabled(key):
            continue
        provider = self._providers.get(key)
        if provider is not None and provider.supports(page_url):
            return key
    raise ProviderNotSupportedError(f"不支持的弹幕来源: {page_url}")
```

不把 `other` 放进匹配范围；它不在 `_provider_order`，因此手动直链不会绕过原生 provider。

- [ ] **Step 4: 运行定向测试和原有 resolve 测试**

Run: `uv run pytest tests/test_danmaku_service.py -k 'provider_key_for_url or resolve_danmu' -v`

Expected: PASS。

- [ ] **Step 5: 提交服务层改动**

```bash
git add src/atv_player/danmaku/service.py tests/test_danmaku_service.py
git commit -m "feat(danmaku): identify provider for episode URL"
```

### Task 2: 通用控制器与直解析控制器支持单集 URL 下载

**Files:**
- Modify: `src/atv_player/danmaku/generic.py:1`
- Modify: `src/atv_player/danmaku/direct_parse.py:127`
- Test: `tests/test_generic_danmaku_controller.py:314`
- Test: `tests/test_direct_parse_danmaku.py:28`

- [ ] **Step 1: 写 URL 校验和通用控制器原子更新的失败测试**

在 `tests/test_generic_danmaku_controller.py` 加入：

```python
import pytest

from atv_player.danmaku.generic import normalize_danmaku_episode_url


@pytest.mark.parametrize("value", ["", "v.qq.com/x/1", "ftp://v.qq.com/x/1", "https:///x/1"])
def test_normalize_danmaku_episode_url_rejects_incomplete_urls(value: str) -> None:
    with pytest.raises(ValueError, match=r"完整的 http\(s\) 单集链接"):
        normalize_danmaku_episode_url(value)


def test_generic_controller_downloads_episode_url_without_replacing_candidates(
    monkeypatch, tmp_path: Path
) -> None:
    class RecordingService:
        def __init__(self) -> None:
            self.resolve_calls: list[str] = []

        def provider_key_for_url(self, page_url: str) -> str:
            assert page_url == "https://v.qq.com/x/cover/demo/ep1.html"
            return "tencent"

        def resolve_danmu(self, page_url: str) -> str:
            self.resolve_calls.append(page_url)
            return '<i><d p="1,1,25,16777215">manual</d></i>'

    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    monkeypatch.setattr(generic_danmaku_module, "load_cached_danmaku_xml", danmaku_cache_module.load_cached_danmaku_xml)
    monkeypatch.setattr(generic_danmaku_module, "save_cached_danmaku_xml", danmaku_cache_module.save_cached_danmaku_xml)
    candidates = [
        DanmakuSourceGroup(
            provider="youku",
            provider_label="优酷",
            options=[DanmakuSourceOption(provider="youku", name="旧候选", url="https://youku/old")],
        )
    ]
    service = RecordingService()
    controller = GenericDanmakuController(service)
    item = PlayItem(
        title="第1集",
        url="https://media.example/1.m3u8",
        vod_id="item-1",
        media_title="成何体统",
        danmaku_search_query="成何体统 1集",
        danmaku_candidates=candidates,
    )

    xml = controller.download_danmaku_from_url(
        item,
        "  https://v.qq.com/x/cover/demo/ep1.html  ",
    )

    assert "manual" in xml
    assert service.resolve_calls == ["https://v.qq.com/x/cover/demo/ep1.html"]
    assert item.danmaku_candidates is candidates
    assert item.selected_danmaku_provider == "tencent"
    assert item.selected_danmaku_url == "https://v.qq.com/x/cover/demo/ep1.html"
    assert item.selected_danmaku_title == "第1集"
```

再写一个失败保持测试：让 `resolve_danmu()` 抛出 `RuntimeError("boom")`，预置旧 `danmaku_xml`、provider、URL 和 title，断言调用失败后四个字段原值不变。

- [ ] **Step 2: 运行通用控制器新测试并确认失败**

Run: `uv run pytest tests/test_generic_danmaku_controller.py -k 'episode_url or downloads_episode_url' -v`

Expected: FAIL，规范化函数和控制器方法尚不存在。

- [ ] **Step 3: 实现 URL 规范化和通用控制器方法**

在 `src/atv_player/danmaku/generic.py` 导入 `urlparse` 并加入：

```python
def normalize_danmaku_episode_url(value: str) -> str:
    normalized = str(value or "").strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请输入完整的 http(s) 单集链接")
    return normalized
```

在 `GenericDanmakuController` 中加入：

```python
def download_danmaku_from_url(self, item: PlayItem, page_url: str) -> str:
    normalized_url = normalize_danmaku_episode_url(page_url)
    provider_key = self._danmaku_service.provider_key_for_url(normalized_url)
    source_title = (item.title or item.media_title or "单集弹幕").strip()
    self._log_danmaku_event("弹幕下载中", detail=f"{provider_key} - {source_title}")
    query_name = item.danmaku_search_query.strip() or self._search_query(item)
    reg_src = self._reg_src(item)
    xml_text = load_cached_danmaku_xml(query_name, normalized_url)
    if not xml_text:
        xml_text = self._danmaku_service.resolve_danmu(normalized_url)
        save_cached_danmaku_xml(query_name, normalized_url, xml_text)
    if reg_src:
        save_cached_danmaku_xml(query_name, reg_src, xml_text)
    item.danmaku_xml = xml_text
    item.selected_danmaku_provider = provider_key
    item.selected_danmaku_url = normalized_url
    item.selected_danmaku_title = source_title
    item.danmaku_error = ""
    self._log_danmaku_event("弹幕下载成功", detail=f"{self._count_danmaku_entries(xml_text)} 条弹幕")
    return xml_text
```

保持所有 `PlayItem` 字段赋值在 provider 识别、缓存/解析和缓存写入之后，确保异常时不覆盖旧状态。

- [ ] **Step 4: 写直解析控制器统一接口的失败测试**

在 `tests/test_direct_parse_danmaku.py` 加入：

```python
def test_direct_parse_controller_downloads_manual_episode_url() -> None:
    calls: list[str] = []
    controller = DirectParseDanmakuController(
        load=lambda url: calls.append(url) or {"danmuku": [[1, "right", "ffffff", "", "manual"]]}
    )
    item = PlayItem(title="第1集", url="https://stream.example/1.m3u8", media_title="成何体统")

    xml = controller.download_danmaku_from_url(item, "https://v.qq.com/x/cover/demo/ep1.html")

    assert calls == ["https://v.qq.com/x/cover/demo/ep1.html"]
    assert "manual" in xml
    assert item.selected_danmaku_provider == "direct_parse"
```

再加入失败恢复测试：预置旧候选、XML、provider、URL 和 title，让 `load` 抛出 `RuntimeError("boom")`，断言这五项在异常后全部保持原值。

- [ ] **Step 5: 确认直解析测试失败并实现接口**

Run: `uv run pytest tests/test_direct_parse_danmaku.py -k 'manual_episode_url' -v`

Expected: FAIL，`download_danmaku_from_url` 不存在。

在 `DirectParseDanmakuController` 加入带快照恢复的适配方法：

```python
def download_danmaku_from_url(self, item: PlayItem, page_url: str) -> str:
    normalized_url = normalize_danmaku_episode_url(page_url)
    previous_source_state = (
        item.danmaku_candidates,
        item.selected_danmaku_provider,
        item.selected_danmaku_url,
        item.selected_danmaku_title,
        item.danmaku_error,
    )
    try:
        return self.switch_danmaku_source(item, normalized_url)
    except Exception:
        (
            item.danmaku_candidates,
            item.selected_danmaku_provider,
            item.selected_danmaku_url,
            item.selected_danmaku_title,
            item.danmaku_error,
        ) = previous_source_state
        raise
```

并从 `atv_player.danmaku.generic` 导入规范化函数。直解析会话继续使用其既有全局解析策略，不改变普通和 Spider 会话的原生 provider 策略。

- [ ] **Step 6: 运行控制器测试**

Run: `uv run pytest tests/test_generic_danmaku_controller.py tests/test_direct_parse_danmaku.py -q`

Expected: PASS。

- [ ] **Step 7: 提交通用和直解析控制器改动**

```bash
git add src/atv_player/danmaku/generic.py src/atv_player/danmaku/direct_parse.py tests/test_generic_danmaku_controller.py tests/test_direct_parse_danmaku.py
git commit -m "feat(danmaku): download episode URL in controllers"
```

### Task 3: Spider 播放控制器实现同一接口

**Files:**
- Modify: `src/atv_player/plugins/controller.py:2082`
- Test: `tests/test_spider_plugin_controller.py:4420`

- [ ] **Step 1: 写 Spider 控制器失败测试**

在现有手动切换测试附近加入：

```python
def test_spider_controller_downloads_episode_url_atomically(monkeypatch) -> None:
    class RecordingService:
        def provider_key_for_url(self, page_url: str) -> str:
            return "tencent"

        def resolve_danmu(self, page_url: str) -> str:
            assert page_url == "https://v.qq.com/x/cover/demo/ep1.html"
            return '<i><d p="1,1,25,16777215">manual</d></i>'

    saved: list[tuple[str, str]] = []
    monkeypatch.setattr(controller_module, "load_cached_danmaku_xml", lambda name, url: "")
    monkeypatch.setattr(
        controller_module,
        "save_cached_danmaku_xml",
        lambda name, url, xml: saved.append((name, url)),
    )
    controller = SpiderPluginController(
        PluginLevelDanmakuSpider(),
        plugin_name="红果短剧",
        search_enabled=True,
        danmaku_service=RecordingService(),
    )
    candidates = [
        DanmakuSourceGroup(
            provider="youku",
            provider_label="优酷",
            options=[DanmakuSourceOption(provider="youku", name="旧候选", url="https://youku/old")],
        )
    ]
    item = PlayItem(
        title="第1集",
        url="https://stream.example/1.m3u8",
        vod_id="item-1",
        media_title="红果短剧",
        danmaku_search_query="红果短剧 1集",
        danmaku_candidates=candidates,
    )

    xml = controller.download_danmaku_from_url(item, "https://v.qq.com/x/cover/demo/ep1.html")

    assert "manual" in xml
    assert item.danmaku_candidates is candidates
    assert item.selected_danmaku_provider == "tencent"
    assert item.selected_danmaku_url == "https://v.qq.com/x/cover/demo/ep1.html"
    assert ("红果短剧 1集", "https://v.qq.com/x/cover/demo/ep1.html") in saved
```

另加解析异常测试，断言已有 XML、provider、URL 和 title 不变。

- [ ] **Step 2: 运行测试并确认接口缺失失败**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k 'download and episode_url' -v`

Expected: FAIL，Spider 控制器没有 `download_danmaku_from_url`。

- [ ] **Step 3: 实现 Spider 控制器方法**

从 `atv_player.danmaku.generic` 导入 `normalize_danmaku_episode_url`。在 `switch_danmaku_source()` 附近加入独立方法：

```python
def download_danmaku_from_url(self, item: PlayItem, page_url: str) -> str:
    normalized_url = normalize_danmaku_episode_url(page_url)
    provider_key = self._danmaku_service.provider_key_for_url(normalized_url)
    source_title = (item.title or item.media_title or "单集弹幕").strip()
    self._log_danmaku_event("弹幕下载中", detail=f"{provider_key} - {source_title}")
    query_name = (item.danmaku_search_query or _build_danmaku_search_name(item)).strip()
    reg_src = str(item.vod_id or item.url or "").strip()
    xml_text = load_cached_danmaku_xml(query_name, normalized_url)
    if not xml_text:
        xml_text = self._resolve_danmaku_xml(normalized_url)
    self._save_danmaku_xml_cache(
        item,
        query_name,
        reg_src,
        xml_text,
        page_url=normalized_url,
    )
    item.danmaku_xml = xml_text
    item.selected_danmaku_provider = provider_key
    item.selected_danmaku_url = normalized_url
    item.selected_danmaku_title = source_title
    item.danmaku_error = ""
    self._save_danmaku_source_preference(item)
    danmaku_count = _count_danmaku_entries(xml_text)
    self._log_danmaku_event("弹幕下载成功", detail=_build_danmaku_success_detail(item, danmaku_count))
    return xml_text
```

缓存和解析先完成，再更新 `PlayItem`；候选列表保持原对象。

- [ ] **Step 4: 运行 Spider 弹幕相关测试**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k 'danmaku' -q`

Expected: PASS。

- [ ] **Step 5: 提交 Spider 控制器改动**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat(danmaku): support episode URLs in spider playback"
```

### Task 4: 弹幕源对话框增加单集链接入口

**Files:**
- Modify: `src/atv_player/ui/player_window.py:769`
- Modify: `src/atv_player/ui/player_window.py:8609`
- Modify: `src/atv_player/ui/player_window.py:8954`
- Test: `tests/test_player_window_ui.py:1765`

- [ ] **Step 1: 写对话框结构和输入校验的失败测试**

在 `tests/test_player_window_ui.py` 的弹幕源对话框测试附近加入：

```python
def test_player_window_danmaku_source_dialog_has_episode_url_download_controls(qtbot) -> None:
    item = PlayItem(title="第1集", url="https://media.example/1.m3u8")
    session = PlayerSession(
        vod=VodItem(vod_id="1", vod_name="红果短剧"),
        playlist=[item],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        danmaku_controller=object(),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(session)
    window._open_danmaku_source_dialog()

    assert window._danmaku_source_url_edit is not None
    assert window._danmaku_source_url_download_button is not None
    assert window._danmaku_source_url_download_button.text() == "下载"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "请输入单集链接"),
        ("v.qq.com/x/1", "请输入完整的 http(s) 单集链接"),
        ("https:///x/1", "请输入完整的 http(s) 单集链接"),
    ],
)
def test_player_window_rejects_invalid_episode_url_without_starting_task(
    qtbot, value: str, message: str
) -> None:
    class RecordingController:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def download_danmaku_from_url(self, item: PlayItem, url: str) -> str:
            self.calls.append(url)
            return ""

    controller = RecordingController()
    item = PlayItem(title="第1集", url="https://media.example/1.m3u8")
    session = PlayerSession(
        vod=VodItem(vod_id="1", vod_name="红果短剧"),
        playlist=[item],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        danmaku_controller=controller,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(session)
    window._open_danmaku_source_dialog()
    window._danmaku_source_url_edit.setText(value)

    window._download_current_item_danmaku_url()

    assert controller.calls == []
    assert window._danmaku_source_status_label.text() == message
```

- [ ] **Step 2: 运行 UI 新测试并确认控件缺失失败**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k 'episode_url_download_controls or rejects_invalid_episode_url' -v`

Expected: FAIL，窗口没有直链控件及提交方法。

- [ ] **Step 3: 添加控件、信号和动作状态**

在 `PlayerWindow.__init__` 增加：

```python
self._danmaku_source_url_edit: QLineEdit | None = None
self._danmaku_source_url_download_button: QPushButton | None = None
```

在 `_ensure_danmaku_source_dialog()` 的搜索布局后加入：

```python
url_row = QHBoxLayout()
url_row.addWidget(QLabel("单集链接", host))
self._danmaku_source_url_edit = QLineEdit(host)
self._danmaku_source_url_edit.setPlaceholderText("https://v.qq.com/...")
url_row.addWidget(self._danmaku_source_url_edit, 1)
self._danmaku_source_url_download_button = QPushButton("下载", host)
url_row.addWidget(self._danmaku_source_url_download_button)
layout.addLayout(url_row)
self._danmaku_source_url_download_button.clicked.connect(
    self._download_current_item_danmaku_url
)
self._danmaku_source_url_edit.returnPressed.connect(
    self._download_current_item_danmaku_url
)
```

在 `_refresh_danmaku_source_dialog_actions()` 中按“存在当前项且没有活动弹幕任务”同步启用输入框和下载按钮。

为 `_start_danmaku_source_task()` 增加默认空值参数 `status_error_prefix: str = ""`。任务捕获异常时构造 `failure_status = f"{status_error_prefix}: {exc}"`；最后一个活动任务结束时，成功则清空状态，失败且提供该参数则把 `failure_status` 保留到 `item.danmaku_status_text`，再发出既有 `finished` 信号。原有调用不传该参数，行为保持不变。

- [ ] **Step 4: 添加提交方法**

从 `atv_player.danmaku.generic` 导入 `normalize_danmaku_episode_url`，并在手动切换方法附近加入：

```python
def _download_current_item_danmaku_url(self) -> None:
    current_item = self._current_play_item()
    session = self.session
    edit = self._danmaku_source_url_edit
    if current_item is None or session is None or edit is None:
        return
    raw_url = edit.text().strip()
    if not raw_url:
        current_item.danmaku_status_text = "请输入单集链接"
        self._refresh_danmaku_source_dialog_actions(current_item)
        return
    try:
        page_url = normalize_danmaku_episode_url(raw_url)
    except ValueError as exc:
        current_item.danmaku_status_text = str(exc)
        self._refresh_danmaku_source_dialog_actions(current_item)
        return
    download = getattr(session.danmaku_controller, "download_danmaku_from_url", None)
    if not callable(download):
        current_item.danmaku_status_text = "当前弹幕源不支持单集链接下载"
        self._refresh_danmaku_source_dialog_actions(current_item)
        return
    current_item.danmaku_status_text = "下载中（单集链接）..."
    self._start_danmaku_source_task(
        current_item,
        error_prefix="单集链接弹幕下载失败",
        status_error_prefix="单集链接弹幕下载失败",
        task=lambda: download(current_item, page_url),
        configure_danmaku_on_success=True,
    )
```

- [ ] **Step 5: 写异步成功、Enter 和按钮状态测试**

加入一个 fake controller，其 `download_danmaku_from_url()` 记录 URL 并设置 XML/provider/URL/title。测试点击下载后：

```python
assert item.danmaku_pending is True
assert window._danmaku_source_url_download_button.isEnabled() is False
qtbot.waitUntil(lambda: controller.calls == ["https://v.qq.com/x/cover/demo/ep1.html"])
qtbot.waitUntil(lambda: item.danmaku_pending is False)
qtbot.waitUntil(lambda: renders == [item.danmaku_xml])
assert item.selected_danmaku_provider == "tencent"
assert window._danmaku_source_url_download_button.isEnabled() is True
```

用 `window._danmaku_source_url_edit.returnPressed.emit()` 再写一个测试，断言 Enter 触发同一路径。失败测试让 controller 抛出 `RuntimeError("boom")`，等待任务结束后断言状态等于“单集链接弹幕下载失败: boom”、日志包含同一错误，且预置的 XML 和来源字段不变。

- [ ] **Step 6: 运行 UI 定向测试并修正最小实现**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k 'danmaku_source and episode_url' -v`

Expected: PASS。

- [ ] **Step 7: 运行整个播放器 UI 测试**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 UI 改动**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat(ui): download danmaku from episode URL"
```

### Task 5: 文档与完整验证

**Files:**
- Modify: `docs/help.md:558`

- [ ] **Step 1: 更新帮助文档**

在“弹幕源对话框”能力列表中增加：

```markdown
- 粘贴受支持视频平台的单集播放页链接，直接下载并立即加载该集弹幕
```

补充一句：未知平台、已禁用来源或解析失败不会替换当前弹幕。

- [ ] **Step 2: 运行格式和静态检查**

Run: `uv run ruff check src/atv_player/danmaku/service.py src/atv_player/danmaku/generic.py src/atv_player/danmaku/direct_parse.py src/atv_player/plugins/controller.py src/atv_player/ui/player_window.py tests/test_danmaku_service.py tests/test_generic_danmaku_controller.py tests/test_direct_parse_danmaku.py tests/test_spider_plugin_controller.py tests/test_player_window_ui.py`

Expected: PASS，无 lint 错误。

Run: `npx --yes pyright src/atv_player/danmaku/service.py src/atv_player/danmaku/generic.py src/atv_player/danmaku/direct_parse.py src/atv_player/plugins/controller.py src/atv_player/ui/player_window.py`

Expected: PASS，无类型错误。

- [ ] **Step 3: 运行功能相关测试集**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_danmaku_service.py tests/test_generic_danmaku_controller.py tests/test_direct_parse_danmaku.py tests/test_spider_plugin_controller.py tests/test_player_window_ui.py -q`

Expected: PASS。

- [ ] **Step 4: 运行完整测试集**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`

Expected: PASS。

- [ ] **Step 5: 检查最终差异和工作区**

Run: `git diff --check`

Expected: 无输出，退出码 0。

Run: `git status --short`

Expected: 仅显示本任务尚未提交的帮助文档，或工作区为空。

- [ ] **Step 6: 提交帮助文档**

```bash
git add docs/help.md
git commit -m "docs: document episode URL danmaku download"
```

- [ ] **Step 7: 最终提交检查**

Run: `git status --short`

Expected: 无输出。

Run: `git log -6 --oneline`

Expected: 包含本计划的服务层、控制器、Spider、UI 和帮助文档提交。
