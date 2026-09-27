"""网络直播实时弹幕:后端 /live/danmaku 增量轮询消费 + mpv OSD 渲染。

协议与行为对齐安卓端 CatVodTVSpider LiveDanmaku.java:
- 以响应 next 为游标增量轮询,首帧不带 after(后端回最近 30 条)只保留末尾几条防刷屏;
  首帧一条都没有时游标保持作废,否则会把后端整段缓冲拉下来刷屏。
- 渲染配置(行数/时长/字号/透明度/单色/人气值开关)随每次轮询热下发。
- 任何环节失败都只是没有弹幕,绝不影响播放:入口吞异常、线程 daemon。

渲染走 mpv 的 osd-overlay(ASS 事件):Wayland/XWayland 下叠在 mpv 原生 wid
窗口上的 Qt 控件无法真正透明(渲染成黑色遮罩),而 mpv 用 libass 自己合成,
天然透明、随窗口缩放、全屏可用。Poller 为纯 Python 便于脱离事件循环测试;
Qt 侧由 player_window 的信号桥把轮询结果转投主线程。
"""

from __future__ import annotations

import colorsys
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtGui import QFont, QFontMetrics

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = ("huya", "douyu", "bili", "douyin", "twitch")

_ROOM_PATTERN = re.compile(r"^([a-z]+)\$(.+)$")


def resolve_live_room(source_kind: object, vod_id: object) -> tuple[str, str] | None:
    """从播放会话身份解析直播间:仅后端 /live 直播间有 platform$roomId 形态的 vod_id。

    自定义 m3u 频道(custom-channel:)与点播源不命中,返回 None。
    """
    if str(source_kind or "").strip() != "live":
        return None
    text = str(vod_id or "").strip()
    match = _ROOM_PATTERN.match(text)
    if match is None or match.group(1) not in SUPPORTED_PLATFORMS:
        return None
    return match.group(1), match.group(2)


@dataclass(frozen=True)
class LiveDanmakuConfig:
    """后端下发的渲染配置(已归一化,语义即最终值)。"""

    enabled: bool = True
    lanes: int = 0
    duration_ms: int = 8000
    font_scale: int = 100
    opacity: int = 100
    color: str = ""
    show_online: bool = True

    @classmethod
    def from_payload(cls, payload: object) -> LiveDanmakuConfig:
        def _int(key: str, fallback: int, low: int, high: int) -> int:
            try:
                value = int(payload.get(key, fallback))  # type: ignore[union-attr]
            except (TypeError, ValueError):
                return fallback
            return max(low, min(high, value))

        if not isinstance(payload, dict):
            return cls()
        color = str(payload.get("color") or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            color = ""
        return cls(
            enabled=bool(payload.get("enabled", True)),
            lanes=_int("lanes", 0, 0, 8),
            duration_ms=_int("duration", 8000, 1000, 120000),
            font_scale=_int("fontSize", 100, 50, 200),
            opacity=_int("opacity", 100, 10, 100),
            color=color,
            show_online=bool(payload.get("showOnline", True)),
        )


@dataclass(frozen=True)
class LiveDanmakuMessage:
    text: str
    color: str


def _parse_messages(
    payload_messages: object,
) -> tuple[list[LiveDanmakuMessage], str | None]:
    bullets: list[LiveDanmakuMessage] = []
    online: str | None = None
    if not isinstance(payload_messages, list):
        return bullets, online
    for item in payload_messages:
        if not isinstance(item, dict):
            continue
        content = str(item.get("message") or "").strip()
        if not content:
            continue
        if str(item.get("type") or "") == "online":
            online = content
        else:
            color = str(item.get("color") or "").strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                color = ""
            bullets.append(LiveDanmakuMessage(text=content, color=color))
    return bullets, online


def normalize_danmaku_color(hex_color: str) -> str:
    """平台原色可读性归一:蓝系/过暗的弹幕色在视频上对比度差,保色相抬亮度。

    无描边渲染下问题最明显(虎牙大量深蓝弹幕),只调亮度、不动色相与
    饱和度;已经很亮的颜色原样返回。空/非法输入返回空串(渲染回落白色)。
    """
    text = (hex_color or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return ""
    if text.upper() == "#0000FF":
        # 虎牙普通弹幕的 fontColor 字段默认值(官网渲染为白色),后端已同步忽略;
        # 客户端兜底,兼容未重建的后端
        return ""
    red = int(text[1:3], 16) / 255.0
    green = int(text[3:5], 16) / 255.0
    blue = int(text[5:7], 16) / 255.0
    hue, light, sat = colorsys.rgb_to_hls(red, green, blue)
    brightest = max(red, green, blue)
    blue_dominant = blue >= red and blue >= green and brightest < 0.85
    if (blue_dominant and light < 0.58) or brightest < 0.55:
        light = max(light, 0.58 if blue_dominant else 0.62)
        red, green, blue = colorsys.hls_to_rgb(hue, light, sat)
    return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def format_online_count(value: str) -> str:
    """人气值文本:数值则压成 万/亿 展示,非数值原样返回。"""
    text = str(value or "").strip()
    try:
        count = float(text)
    except ValueError:
        return text
    if count >= 100_000_000:
        return f"{count / 100_000_000:.1f}亿"
    if count >= 10_000:
        return f"{count / 10_000:.1f}万"
    return str(int(count))


@dataclass
class LiveDanmakuSink:
    """轮询结果出口;poll_once/run 在后台线程调用这些回调。"""

    on_config: Callable[[LiveDanmakuConfig], None]
    on_batch: Callable[[list[LiveDanmakuMessage], str | None], None]
    on_stopped: Callable[[str], None] = lambda _reason: None


class LiveDanmakuPoller:
    """直播弹幕轮询器:每 INTERVAL 秒拉一次增量,退避与放弃策略与安卓端一致。"""

    INTERVAL_SECONDS = 2.0
    MAX_BACKOFF_SECONDS = 30.0
    MAX_FAILURES = 10
    FIRST_BATCH = 6

    def __init__(
        self,
        platform: str,
        room_id: str,
        fetch: Callable[[str, str, int | None], dict | None],
        sink: LiveDanmakuSink,
        *,
        interval_seconds: float = INTERVAL_SECONDS,
    ) -> None:
        self._platform = platform
        self._room_id = room_id
        self._fetch = fetch
        self._sink = sink
        self._interval = interval_seconds
        # None 表示下次按首帧处理(不带 after,只取末尾几条)
        self._cursor: int | None = None
        self._failures = 0
        self._delay = interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._stopped_reason: str | None = None

    @property
    def room_key(self) -> str:
        return f"{self._platform}${self._room_id}"

    @property
    def running(self) -> bool:
        thread = self._thread
        return (
            thread is not None and thread.is_alive() and not self._stop_event.is_set()
        )

    @property
    def next_delay_seconds(self) -> float:
        return self._delay

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._stopped_reason = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"live-danmaku-{self._platform}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 - 弹幕失败绝不影响播放
                logger.exception("live danmaku poll loop error: %s", self.room_key)
                self._backoff()
            if self._stopped_reason is not None or self._stop_event.is_set():
                break
            self._stop_event.wait(self._delay)

    def poll_once(self) -> None:
        """单轮拉取;测试可直接调用以确定性驱动。"""
        if self._stop_event.is_set():
            return
        try:
            payload = self._fetch(self._platform, self._room_id, self._cursor)
        except Exception as exc:  # noqa: BLE001 - 网络抖动按退避处理
            logger.debug("live danmaku fetch failed: %s: %s", self.room_key, exc)
            self._backoff()
            return
        if not isinstance(payload, dict):
            self._backoff()
            return
        if payload.get("support") is False:
            logger.info("live danmaku unsupported: %s", self.room_key)
            self._finish("unsupported")
            return
        config = LiveDanmakuConfig.from_payload(payload.get("config"))
        self._sink.on_config(config)
        messages = payload.get("messages")
        bullets, online = _parse_messages(messages)
        first = self._cursor is None
        if first and len(bullets) > self.FIRST_BATCH:
            bullets = bullets[-self.FIRST_BATCH :]
        # 首帧遇上后端刚建上游连接、一条都没有:游标保持作废,下轮继续按首帧取末尾几条
        if not first or len(messages or []) > 0:
            next_cursor = payload.get("next")
            if isinstance(next_cursor, int):
                self._cursor = next_cursor
            else:
                self._cursor = max(self._cursor or 0, 0)
        self._succeed()
        if bullets or online is not None:
            self._sink.on_batch(bullets, online)

    def _succeed(self) -> None:
        self._failures = 0
        self._delay = self._interval

    def _backoff(self) -> None:
        self._failures += 1
        factor = 2 ** min(4, self._failures)
        self._delay = min(self.MAX_BACKOFF_SECONDS, self._interval * factor)
        if self._failures >= self.MAX_FAILURES:
            logger.info(
                "live danmaku give up after %d failures: %s",
                self._failures,
                self.room_key,
            )
            self._finish("giveup")

    def _finish(self, reason: str) -> None:
        self._stopped_reason = reason
        self._stop_event.set()
        self._sink.on_stopped(reason)


@dataclass
class _Bullet:
    text: str
    color: str
    x: float = 0.0
    width: float = 0.0
    lane: int = 0


@dataclass
class _OverlayState:
    """overlay 可测试的纯逻辑状态:轨分配与批内均匀注入节奏。"""

    lanes: int = 0
    width: int = 0
    height: int = 0
    active: list[_Bullet] = field(default_factory=list)
    pending: list[_Bullet] = field(default_factory=list)
    lane_tails: list[_Bullet | None] = field(default_factory=list)
    next_inject_at: float = 0.0
    inject_step_ms: float = 200.0
    max_active = 40
    max_pending = 100

    def relayout(self, lanes: int, width: int, height: int) -> None:
        self.lanes = max(1, min(8, lanes)) if lanes > 0 else 0
        self.width = max(1, width)
        self.height = max(1, height)
        self.active.clear()
        self.pending.clear()
        self.lane_tails = [None] * (self.lanes or 1)

    def feed(
        self,
        bullets: list[_Bullet],
        now_ms: float,
        poll_interval_ms: float,
    ) -> None:
        for bullet in bullets:
            if len(self.pending) >= self.max_pending:
                self.pending.pop(0)
            self.pending.append(bullet)
        # 一次轮询到手的整批在下个轮询周期内均匀铺开,否则每 2 秒瀑布式刷一屏
        if self.pending:
            step = poll_interval_ms / len(self.pending)
            self.inject_step_ms = max(60.0, min(600.0, step))
        if not self.active:
            self.next_inject_at = now_ms

    def inject(self, now_ms: float, gap: float, measure) -> int:
        """按节奏把 pending 放上轨道;measure 提供文本宽度。返回注入条数。"""
        injected = 0
        while self.pending and now_ms >= self.next_inject_at:
            bullet = self.pending.pop(0)
            if self._emit(bullet, gap, measure):
                injected += 1
            self.next_inject_at = now_ms + self.inject_step_ms
        return injected

    def _emit(self, bullet: _Bullet, gap: float, measure) -> bool:
        if self.lanes == 0 or len(self.active) >= self.max_active:
            return False
        limit = self.width - gap
        for lane in range(self.lanes):
            last = self.lane_tails[lane]
            if last is not None and last.x + last.width > limit:
                continue
            bullet.width = measure(bullet)
            bullet.x = float(self.width)
            bullet.lane = lane
            self.lane_tails[lane] = bullet
            self.active.append(bullet)
            return True
        # 满轨直接丢弃:排队等轨只会让弹幕越积越滞后
        return False

    def advance(self, elapsed_ms: float, speed_px_per_ms: float) -> None:
        for bullet in self.active:
            bullet.x -= speed_px_per_ms * elapsed_ms
        self.active = [b for b in self.active if b.x + b.width > 0]
        if not self.active:
            self.lane_tails = [None] * len(self.lane_tails)

    def idle(self) -> bool:
        return not self.active and not self.pending



def _ass_escape(text: str) -> str:
    """ASS 文本转义:覆写指令的大括号/反斜杠替换为全角,换行折叠为空格。"""
    return (
        text.replace("\\", "＼")
        .replace("{", "｛")
        .replace("}", "｝")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _ass_color(hex_color: str, opacity: int) -> str:
    """#RRGGBB → ASS &HBBGGRR& + \alpha 透明度(0=不透明)。"""
    red, green, blue = 255, 255, 255
    text = hex_color.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        red = int(text[1:3], 16)
        green = int(text[3:5], 16)
        blue = int(text[5:7], 16)
    alpha = round(255 * (1 - opacity / 100.0))
    return f"&H{blue:02X}{green:02X}{red:02X}&", f"&H{alpha:02X}&"


class LiveDanmakuRenderer:
    """实时弹幕渲染器:帧循环把弹幕排版成 ASS 事件,交给 mpv osd-overlay 显示。

    Wayland/XWayland 下叠在 mpv 原生 wid 窗口上的 Qt 控件无法真正透明
    (一律渲染成黑色遮罩),因此弹幕必须画进 mpv 自己的 OSD 里:mpv 用
    libass 合成,天然透明、随窗口缩放、全屏可用。渲染器只产出
    (ass_data, res_w, res_h),由播放层转发给 mpv,不持有任何窗口。
    """

    FRAME_INTERVAL_MS = 33
    POLL_INTERVAL_MS = 2000.0
    # 弹幕穿屏时长相对后端配置的放大倍数:越大滚动越慢
    SCROLL_SLOWDOWN = 2.0

    def __init__(self, present: Callable[[str | None, int, int], None]) -> None:
        self._present = present
        self._config = LiveDanmakuConfig()
        self._state = _OverlayState()
        self._online = ""
        self._last_frame_ms = 0.0
        self._canvas_w = 0
        self._canvas_h = 0
        self._font = QFont()
        self._line_height = 20.0
        self._top_offset = 8.0
        self._gap = 16.0
        self._speed = 0.1  # px/ms,_relayout 按画布宽/时长重算
        # 渲染循环在独立线程:mpv 忙于解码时同步命令往返延迟尖峰会把
        # UI 线程上的 30fps 动画打成卡顿;字体测量只在本线程(UI)做,
        # 工作线程仅做纯数值推进与字符串拼装。
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._idle_notified = False

    # ── 对外接口 ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="live-danmaku-osd", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def set_canvas_size(self, width: int, height: int) -> None:
        with self._lock:
            if width == self._canvas_w and height == self._canvas_h:
                return
            self._canvas_w = max(1, width)
            self._canvas_h = max(1, height)
            self._relayout()

    def apply_config(self, config: LiveDanmakuConfig) -> None:
        with self._lock:
            relayout_keys = (config.lanes, config.font_scale) != (
                self._config.lanes,
                self._config.font_scale,
            )
            self._config = config
            canvas = (self._canvas_w, self._canvas_h)
            if not config.enabled:
                # 关闭只清空画面:轮询继续,网页上重新打开无需重进直播间
                self._clear_locked()
                disabled = True
            else:
                disabled = False
                if self._canvas_w > 0 and (relayout_keys or self._state.lanes == 0):
                    self._relayout()
                elif self._canvas_w > 0:
                    self._speed = self._canvas_w / max(1.0, float(config.duration_ms))
        if disabled:
            self._present(None, canvas[0], canvas[1])
        else:
            self._render_frame(canvas=canvas)

    def feed(self, bullets: list[LiveDanmakuMessage], online: str | None) -> None:
        with self._lock:
            if not self._config.enabled:
                return
            now_ms = time.monotonic() * 1000.0
            metrics = QFontMetrics(self._font)
            batch = [
                _Bullet(text=m.text, color=normalize_danmaku_color(m.color))
                for m in bullets
            ]
            for bullet in batch:
                bullet.width = float(metrics.horizontalAdvance(bullet.text))
            if batch:
                self._state.feed(batch, now_ms, self.POLL_INTERVAL_MS)
            if online is not None:
                self._online = (
                    format_online_count(online) if self._config.show_online else ""
                )
            self._idle_notified = False

    def clear(self) -> None:
        with self._lock:
            self._clear_locked()
            canvas = (self._canvas_w, self._canvas_h)
        self._present(None, canvas[0], canvas[1])

    # ── 内部 ──────────────────────────────────────────────────────────

    def _clear_locked(self) -> None:
        self._state = _OverlayState()
        self._online = ""
        self._last_frame_ms = 0.0
        self._idle_notified = True

    def _relayout(self) -> None:
        height = self._canvas_h
        size = max(12.0, min(34.0, height * 0.032)) * self._config.font_scale / 100.0
        self._font.setPixelSize(max(9, int(round(size))))
        metrics = QFontMetrics(self._font)
        self._line_height = size * 1.45
        # 首行预留给右上角人气角标
        self._top_offset = 8.0 + self._line_height
        self._gap = max(16.0, size)
        # 滚动偏慢:后端时长档再乘 1.5(正常档 8s → 12s 穿屏),接近直播平台官方客户端的节奏
        self._speed = float(self._canvas_w) / (
            max(1.0, float(self._config.duration_ms)) * self.SCROLL_SLOWDOWN
        )
        if self._config.lanes > 0:
            lanes = self._config.lanes
        else:
            lanes = max(3, min(6, int(height * 0.42 / self._line_height)))
        self._state.relayout(lanes, self._canvas_w, height)
        # 字号变了,存量弹幕宽度重测(工作线程只读预计算宽度)
        for bullet in [*self._state.active, *self._state.pending]:
            bullet.width = float(metrics.horizontalAdvance(bullet.text))

    def _run_loop(self) -> None:
        interval = self.FRAME_INTERVAL_MS / 1000.0
        next_frame = time.monotonic()
        while not self._stop_event.is_set():
            self._tick()
            next_frame += interval
            delay = next_frame - time.monotonic()
            if delay < -0.2:
                # 落后太多(系统休眠/长阻塞):重置节奏,避免追帧连跳
                next_frame = time.monotonic()
                delay = 0.0
            self._stop_event.wait(max(0.0, delay))

    def _tick(self) -> None:
        with self._lock:
            now_ms = time.monotonic() * 1000.0
            # 掉帧/长时间未绘制时钳住步进,避免弹幕瞬移
            last = self._last_frame_ms
            elapsed = 0.0 if last == 0.0 else min(now_ms - last, 120.0)
            self._last_frame_ms = now_ms
            self._state.inject(now_ms, self._gap, lambda bullet: bullet.width)
            self._state.advance(elapsed, self._speed)
            if self._state.idle() and not self._online:
                self._last_frame_ms = 0.0
                canvas = (self._canvas_w, self._canvas_h)
                notify_idle = not self._idle_notified
                self._idle_notified = True
                snapshot = None
            else:
                canvas = (self._canvas_w, self._canvas_h)
                snapshot = [
                    (bullet.text, bullet.color, bullet.x, bullet.lane)
                    for bullet in self._state.active
                ]
        if snapshot is None:
            if notify_idle:
                self._present(None, canvas[0], canvas[1])
            return
        self._render_frame(snapshot, canvas)

    def _render_frame(
        self,
        snapshot: list[tuple[str, str, float, int]] | None = None,
        canvas: tuple[int, int] | None = None,
    ) -> None:
        """排版当前帧为 ASS 事件行并交付 mpv;\an7 左上锚定,坐标即画布像素。

        snapshot/canvas 由工作线程在锁内拷贝后传入;UI 线程直接调用
        (apply_config)时在锁内自取。拼装与 mpv 命令都在锁外执行。
        """
        with self._lock:
            if not self._config.enabled or self._canvas_w <= 0:
                return
            if canvas is None:
                canvas = (self._canvas_w, self._canvas_h)
            if snapshot is None:
                snapshot = [
                    (bullet.text, bullet.color, bullet.x, bullet.lane)
                    for bullet in self._state.active
                ]
            opacity = self._config.opacity
            override = self._config.color
            font_size = self._font.pixelSize()
            online = self._online
            top_offset = self._top_offset
            line_height = self._line_height
        events: list[str] = []
        for text, color_hex, x, lane in snapshot:
            color, alpha = _ass_color(override or color_hex, opacity)
            top = top_offset + lane * line_height
            # x 允许为负:文字滚出左边界由 OSD 裁剪,钳到 0 会让弹幕卡在左边缘
            tag = f"\\an7\\pos({int(x)},{max(0, int(top))})"
            style = f"\\c{color}\\alpha{alpha}\\fs{font_size}"
            events.append("{" + tag + style + "}" + _ass_escape(text))
        if online:
            color, alpha = _ass_color("#FFFFFF", opacity)
            tag = f"\\an9\\pos({canvas[0] - 10},8)"
            style = f"\\c{color}\\alpha{alpha}\\fs{font_size}"
            events.append("{" + tag + style + "}" + _ass_escape(online))
        self._present(chr(10).join(events), canvas[0], canvas[1])

