"""直播实时弹幕:房间解析、配置归一化、轮询器游标/退避协议、人气格式化与轨分配逻辑。

对齐后端 LiveDanmakuController 的接口契约与安卓端 LiveDanmaku.java 的消费语义,
poller 用可注入 fetch 直接驱动 poll_once,不依赖线程与 Qt 事件循环。
"""

from __future__ import annotations

from atv_player.live_danmaku import (
    LiveDanmakuConfig,
    LiveDanmakuMessage,
    LiveDanmakuPoller,
    LiveDanmakuSink,
    _OverlayState,
    format_online_count,
    resolve_live_room,
)


class RecordingSink:
    def __init__(self) -> None:
        self.configs: list[LiveDanmakuConfig] = []
        self.batches: list[tuple[list[LiveDanmakuMessage], str | None]] = []
        self.stopped: list[str] = []

    def as_sink(self) -> LiveDanmakuSink:
        return LiveDanmakuSink(
            on_config=self.configs.append,
            on_batch=lambda bullets, online: self.batches.append((bullets, online)),
            on_stopped=self.stopped.append,
        )


class FakeFetch:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, str, int | None]] = []

    def __call__(self, platform: str, room_id: str, after: int | None):
        self.calls.append((platform, room_id, after))
        if not self.payloads:
            raise AssertionError("unexpected extra fetch")
        item = self.payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _payload(
    messages: list[dict] | None = None,
    next_cursor: int = 0,
    support: bool = True,
    config: dict | None = None,
) -> dict:
    return {
        "success": True,
        "platform": "huya",
        "roomId": "123",
        "support": support,
        "config": config if config is not None else {},
        "messages": messages or [],
        "next": next_cursor,
    }


def _chat(seq: int, text: str = "hello", color: str = "") -> dict:
    message = {"seq": seq, "userName": "u", "message": text, "type": "chat"}
    if color:
        message["color"] = color
    return message


def make_poller(fetch, sink=None, interval: float = 2.0):
    sink = sink or RecordingSink()
    poller = LiveDanmakuPoller(
        "huya", "123", fetch, sink.as_sink(), interval_seconds=interval
    )
    return poller, sink


# ── 房间解析 ─────────────────────────────────────────────────────────────


def test_resolve_live_room_accepts_supported_platforms():
    assert resolve_live_room("live", "douyu$8888") == ("douyu", "8888")
    assert resolve_live_room("live", "twitch$streamer") == ("twitch", "streamer")


def test_resolve_live_room_rejects_unsupported_or_malformed():
    assert resolve_live_room("live", "custom-channel:cctv1") is None
    assert resolve_live_room("live", "youtube$abc") is None
    assert resolve_live_room("live", "huya") is None
    assert resolve_live_room("live", "huya$") is None
    assert resolve_live_room("browse", "douyu$8888") is None
    assert resolve_live_room("", "douyu$8888") is None
    assert resolve_live_room("live", "") is None


# ── 配置归一化 ───────────────────────────────────────────────────────────


def test_config_defaults_when_payload_missing():
    config = LiveDanmakuConfig.from_payload(None)
    assert config == LiveDanmakuConfig()
    assert config.enabled is True
    assert config.lanes == 0
    assert config.duration_ms == 8000


def test_config_clamps_out_of_range_values():
    config = LiveDanmakuConfig.from_payload(
        # noqa: E501 - 单行便于对照字段
        {"lanes": 99, "duration": 10, "fontSize": 500, "opacity": 1, "color": "#xyz",
         "enabled": False}
    )
    assert config.lanes == 8
    assert config.duration_ms == 1000
    assert config.font_scale == 200
    assert config.opacity == 10
    assert config.color == ""
    assert config.enabled is False


def test_config_accepts_valid_color_and_flags():
    config = LiveDanmakuConfig.from_payload({"color": "#FF8800", "showOnline": False})
    assert config.color == "#FF8800"
    assert config.show_online is False


# ── 轮询协议 ─────────────────────────────────────────────────────────────


def test_first_poll_has_no_after_and_trims_first_batch():
    fetch = FakeFetch([_payload([_chat(i) for i in range(10)], next_cursor=9)])
    poller, sink = make_poller(fetch)
    poller.poll_once()

    assert fetch.calls[0] == ("huya", "123", None)
    assert len(sink.batches) == 1
    bullets, online = sink.batches[0]
    assert [b.text for b in bullets] == ["hello"] * 6
    assert online is None
    assert fetch.calls[0][2] is None


def test_cursor_advances_with_next_and_second_poll_uses_after():
    fetch = FakeFetch([
        _payload([_chat(1)], next_cursor=5),
        _payload([_chat(6, text="second")], next_cursor=6),
    ])
    poller, sink = make_poller(fetch)
    poller.poll_once()
    poller.poll_once()

    assert fetch.calls[0][2] is None
    assert fetch.calls[1][2] == 5
    assert sink.batches[1][0][0].text == "second"


def test_empty_first_frame_keeps_cursor_invalid():
    fetch = FakeFetch([
        _payload([], next_cursor=0),
        _payload([_chat(3)], next_cursor=3),
    ])
    poller, sink = make_poller(fetch)
    poller.poll_once()
    assert sink.batches == []

    poller.poll_once()
    # 第二轮仍按首帧(不带 after),避免把整段缓冲拉下来刷屏
    assert fetch.calls[1][2] is None
    assert len(sink.batches) == 1


def test_online_message_not_a_bullet_but_delivered():
    messages = [
        {"seq": 1, "userName": "", "message": "12345", "type": "online"},
        _chat(2, text="hi"),
    ]
    payload = _payload(messages, next_cursor=2)
    fetch = FakeFetch([payload])
    poller, sink = make_poller(fetch)
    poller.poll_once()

    bullets, online = sink.batches[0]
    assert [b.text for b in bullets] == ["hi"]
    assert online == "12345"


def test_unsupported_platform_stops_poller():
    fetch = FakeFetch([_payload(support=False)])
    poller, sink = make_poller(fetch)
    poller.poll_once()

    assert sink.stopped == ["unsupported"]
    fetch.calls.clear()
    poller.poll_once()
    assert fetch.calls == []


def test_server_disabled_still_polls_and_emits_config():
    fetch = FakeFetch(
        [
            _payload([], next_cursor=0, config={"enabled": False}),
            _payload([], next_cursor=0, config={"enabled": False}),
        ]
    )
    poller, sink = make_poller(fetch)
    poller.poll_once()
    poller.poll_once()

    assert sink.configs and sink.configs[-1].enabled is False
    assert sink.batches == []
    assert sink.stopped == []


def test_fetch_failure_backs_off_then_recovers():
    fetch = FakeFetch([RuntimeError("boom"), _payload([_chat(1)], next_cursor=1)])
    poller, sink = make_poller(fetch)
    poller.poll_once()

    assert sink.batches == []
    assert poller.next_delay_seconds == 4.0  # 2s * 2^1

    poller.poll_once()
    assert poller.next_delay_seconds == 2.0
    assert len(sink.batches) == 1


def test_consecutive_failures_give_up():
    fetch = FakeFetch([RuntimeError("down")] * 10)
    poller, sink = make_poller(fetch)
    for _ in range(10):
        poller.poll_once()

    assert sink.stopped == ["giveup"]
    assert poller.next_delay_seconds == 30.0


def test_backoff_caps_at_max():
    fetch = FakeFetch([RuntimeError("down")] * 6)
    poller, _sink = make_poller(fetch)
    for _ in range(6):
        poller.poll_once()

    assert poller.next_delay_seconds == 30.0


# ── 人气格式化 ───────────────────────────────────────────────────────────


def test_format_online_count():
    assert format_online_count("999") == "999"
    assert format_online_count("12345") == "1.2万"
    assert format_online_count("123456789") == "1.2亿"
    assert format_online_count("not-a-number") == "not-a-number"
    assert format_online_count("") == ""


# ── 弹幕颜色可读性归一 ─────────────────────────────────────────────────


def test_normalize_color_lightens_dark_blue_keeps_hue():
    from atv_player.live_danmaku import normalize_danmaku_color

    # 虎牙普通弹幕的 fontColor 默认值是纯蓝,官网按白色渲染 → 客户端回落白色
    assert normalize_danmaku_color("#0000FF") == ""

    # 虎牙深蓝:保色相抬亮度,结果仍是蓝系且更亮
    original = "#0055CC"
    adjusted = normalize_danmaku_color(original)
    assert adjusted != original
    o_b = int(original[5:7], 16)
    a_b = int(adjusted[5:7], 16)
    a_r = int(adjusted[1:3], 16)
    assert a_b > a_r  # 仍蓝主色
    assert a_b >= o_b or a_r > 0  # 更亮


def test_normalize_color_keeps_bright_colors():
    from atv_player.live_danmaku import normalize_danmaku_color

    for color in ("#FFFFFF", "#FF0000", "#66CCFF", "#FFD700"):
        assert normalize_danmaku_color(color) == color


def test_normalize_color_lightens_any_too_dark_color():
    from atv_player.live_danmaku import normalize_danmaku_color

    adjusted = normalize_danmaku_color("#202020")
    assert int(adjusted[1:3], 16) > 0x20

    assert normalize_danmaku_color("#xyz") == ""
    assert normalize_danmaku_color("") == ""


# ── 轨分配/注入节奏(纯逻辑) ────────────────────────────────────────────


def test_overlay_state_injects_one_bullet_per_step_window():
    state = _OverlayState()
    state.relayout(lanes=4, width=1000, height=600)
    bullets = [_Bullet_probe(str(i), 100.0) for i in range(5)]
    state.feed(bullets, now_ms=0.0, poll_interval_ms=2000.0)
    assert state.inject_step_ms == 400.0  # 2000 / 5

    injected = state.inject(now_ms=0.0, gap=16.0, measure=lambda b: b.width)
    assert injected == 1
    injected = state.inject(now_ms=100.0, gap=16.0, measure=lambda b: b.width)
    assert injected == 0
    injected = state.inject(now_ms=400.0, gap=16.0, measure=lambda b: b.width)
    assert injected == 1
    assert all(b.x == 1000.0 for b in state.active)


def test_overlay_state_drops_when_lanes_busy():
    state = _OverlayState()
    state.relayout(lanes=1, width=1000, height=600)
    bullets = [_Bullet_probe(str(i), 400.0) for i in range(3)]
    state.feed(bullets, now_ms=0.0, poll_interval_ms=2000.0)

    assert state.inject(0.0, 16.0, lambda b: b.width) == 1
    # 唯一轨道的上一条还没完全进入画面:下一个注入窗口尝试的弹幕被丢弃
    assert state.inject(10_000.0, 16.0, lambda b: b.width) == 0
    assert len(state.active) == 1
    assert [b.text for b in state.pending] == ["2"]


def test_overlay_state_pending_cap():
    state = _OverlayState()
    state.relayout(lanes=1, width=1000, height=600)
    bullets = [_Bullet_probe(str(i), 400.0) for i in range(130)]
    state.feed(bullets, now_ms=0.0, poll_interval_ms=2000.0)
    assert len(state.pending) == state.max_pending


def test_overlay_state_advance_removes_offscreen():
    state = _OverlayState()
    state.relayout(lanes=2, width=1000, height=600)
    state.feed([_Bullet_probe("a", 100.0)], now_ms=0.0, poll_interval_ms=2000.0)
    state.inject(0.0, 16.0, lambda b: b.width)
    assert len(state.active) == 1

    state.advance(elapsed_ms=10_000.0, speed_px_per_ms=0.2)
    assert state.active == []
    assert state.idle()


def _Bullet_probe(text: str, width: float):
    from atv_player.live_danmaku import _Bullet

    return _Bullet(text=text, color="", width=width)


# ── mpv OSD 渲染器(ASS 事件产出) ─────────────────────────────────────


def test_renderer_produces_ass_events(qtbot):
    from atv_player.live_danmaku import LiveDanmakuRenderer

    presented: list[tuple[str | None, int, int]] = []
    renderer = LiveDanmakuRenderer(lambda data, w, h: presented.append((data, w, h)))
    renderer.set_canvas_size(1280, 720)
    renderer.apply_config(LiveDanmakuConfig())
    renderer.feed([LiveDanmakuMessage(text="你好直播", color="#FF0000")], "12345")
    renderer._tick()

    data, width, height = presented[-1]
    assert (width, height) == (1280, 720)
    assert "你好直播" in data
    assert "\\an7\\pos(" in data
    # #RRGGBB → ASS &HBBGGRR&,纯红为 &H0000FF&
    assert "\\c&H0000FF&" in data
    # 人气角标右上角锚定
    assert "\\an9" in data and "1.2万" in data


def test_renderer_keeps_scrolling_past_left_edge(qtbot):
    from atv_player.live_danmaku import LiveDanmakuRenderer

    presented: list[tuple[str | None, int, int]] = []
    renderer = LiveDanmakuRenderer(lambda data, w, h: presented.append((data, w, h)))
    renderer.set_canvas_size(1280, 720)
    renderer.apply_config(LiveDanmakuConfig())
    renderer.feed([LiveDanmakuMessage(text="滚出屏幕的弹幕", color="")], None)
    renderer._tick()
    # 把弹幕推到左边界外但右沿仍在屏内:坐标必须为负(交给 OSD 裁剪),
    # 钳到 0 会让弹幕卡死在左边缘
    bullet = renderer._state.active[0]
    bullet.x = -float(bullet.width) + 5.0
    renderer._tick()
    assert "\\pos(-" in presented[-1][0]


def test_renderer_clears_when_idle_without_badge(qtbot):
    from atv_player.live_danmaku import LiveDanmakuRenderer

    presented: list[tuple[str | None, int, int]] = []
    renderer = LiveDanmakuRenderer(lambda data, w, h: presented.append((data, w, h)))
    renderer.set_canvas_size(1280, 720)
    renderer.apply_config(LiveDanmakuConfig())
    renderer.feed([LiveDanmakuMessage(text="只有弹幕", color="")], None)
    renderer._tick()
    assert presented[-1][0]

    # 弹幕全部飞出画面且无角标:交付 None 清掉 mpv 的 osd-overlay
    renderer._state.advance(100000.0, speed_px_per_ms=1.0)
    renderer._tick()
    assert presented[-1][0] is None
    assert renderer._idle_notified

    # 有角标则保留最后一帧(静态内容,不再动画)
    renderer.feed([], "999999")
    renderer._tick()
    assert presented[-1][0] and "100.0万" in presented[-1][0]


def test_renderer_disabled_clears_output(qtbot):
    from atv_player.live_danmaku import LiveDanmakuRenderer

    presented: list[tuple[str | None, int, int]] = []
    renderer = LiveDanmakuRenderer(lambda data, w, h: presented.append((data, w, h)))
    renderer.set_canvas_size(1280, 720)
    renderer.apply_config(LiveDanmakuConfig())
    renderer.feed([LiveDanmakuMessage(text="被关闭", color="")], None)
    renderer._tick()
    assert presented[-1][0]

    # 服务端关闭:清空画面,轮询仍由上层继续
    renderer.apply_config(LiveDanmakuConfig(enabled=False))
    assert renderer._state.idle()
    assert presented[-1][0] is None
    count_after_clear = len(presented)
    renderer.feed([LiveDanmakuMessage(text="不应出现", color="")], None)
    assert len(presented) == count_after_clear  # feed 被 enabled 门控,不产出新帧


def test_renderer_thread_lifecycle(qtbot):
    import time

    from atv_player.live_danmaku import LiveDanmakuRenderer

    presented: list[tuple[str | None, int, int]] = []
    renderer = LiveDanmakuRenderer(lambda data, w, h: presented.append((data, w, h)))
    renderer.set_canvas_size(1280, 720)
    renderer.apply_config(LiveDanmakuConfig())
    renderer.feed([LiveDanmakuMessage(text="线程滚动", color="")], None)
    renderer.start()
    time.sleep(0.3)
    renderer.stop()
    frames = [data for data, _w, _h in presented if data]
    assert frames and "线程滚动" in frames[0]
    # 停止后再清屏:最后一帧是清除指令
    renderer.clear()
    assert presented[-1][0] is None
