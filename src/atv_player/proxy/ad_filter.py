"""m3u8 媒体播放列表智能广告过滤。

参考 freebox SmartM3u8AdFilterHandler 的三层策略并做了保守化修正:
1. URL 标记过滤(原有 is_ad_segment 规则);
2. 数字序号过滤: 内容分片通常以递增数字命名, 序号中断且之后严格恢复的短分片串视为广告;
3. 命名长度过滤: 命名长度高度一致时, 偏离众数的短分片串视为广告;
4. 正态分布分段统计: 按 #EXT-X-DISCONTINUITY 分块, ts 数明显低于均值的块视为广告块。

安全约束: 智能策略只作用于 VOD 列表(含 #EXT-X-ENDLIST), 直播列表仅保留 URL 标记过滤;
首个产生删除的策略即生效; 单策略删除比例受 MAX_TOTAL_DROP_RATIO 限制;
任何情况下都不会清空全部分片。
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from atv_player.proxy.adblock import is_ad_segment

logger = logging.getLogger(__name__)

MODE_OFF = "off"
MODE_MARKERS = "markers"
MODE_SMART = "smart"
AD_FILTER_MODES = (MODE_OFF, MODE_MARKERS, MODE_SMART)
DEFAULT_AD_FILTER_MODE = MODE_SMART

# 智能策略门槛(取值对照参考实现: minLineCountForFilter=30 行、
# allowedMaxDeviationCount=1/12、dynamicThresholdFactor=0.3、minNormalSegmentCount=7)
MIN_SEGMENTS = 12              # 分片数低于该值不启用智能策略
MAX_AD_RUN = 8                 # 单个广告分片串的最大长度, 超过视为内容而非广告
DIGIT_NUMBERED_RATIO = 0.6     # 数字命名分片的最低占比
DIGIT_CHAIN_COVERAGE = 0.5     # 递增主链需覆盖的数字分片比例
LENGTH_DOMINANCE = 0.85        # 命名长度众数的最低占比
STATS_MIN_BLOCKS = 3           # 分段统计所需的最少 DISCONTINUITY 分块数
STATS_FACTOR = 0.3             # 动态阈值因子(均值 - 标准差 * 因子)
STATS_FLOOR = 3                # 动态阈值下限
STATS_CAP = 14                 # 动态阈值上限(2 * 参考实现 minNormalSegmentCount=7)
MAX_TOTAL_DROP_RATIO = 0.3     # 单一策略最多允许删除的分片比例, 超过视为误判并放弃
KEY_ROTATION_LIMIT = 3         # 不同 KEY URI 数达到该值时禁用分段统计过滤

# 标志"分片区间开始"的分片级标签; 其余标签属于播放列表头
_SEGMENT_TAG_PREFIXES = (
    "#EXTINF",
    "#EXT-X-KEY",
    "#EXT-X-MAP",
    "#EXT-X-BYTERANGE",
    "#EXT-X-PROGRAM-DATE-TIME",
)
_DIGIT_RUN_RE = re.compile(r"\d+")
_KEY_URI_RE = re.compile(r'#EXT-X-KEY:[^\n]*?URI="([^"]+)"')


@dataclass(slots=True)
class ParsedSegment:
    uri_line: str
    absolute_url: str
    duration: float | None
    extinf_line: str | None
    tags: list[str]
    block_index: int


@dataclass(slots=True)
class ParsedPlaylist:
    header_lines: list[str] = field(default_factory=list)
    segments: list[ParsedSegment] = field(default_factory=list)
    trailing_lines: list[str] = field(default_factory=list)
    is_vod: bool = False
    has_key_tags: bool = False


@dataclass(slots=True, frozen=True)
class FilterResult:
    kept: list[bool]
    removed_count: int
    strategy: str


def parse_media_playlist(
    lines: list[str], resolve_uri: Callable[[str], str]
) -> ParsedPlaylist:
    """把媒体播放列表行解析为头标签 + 分片 + 尾标签。

    分片级标签(KEY/MAP/BYTERANGE/PROGRAM-DATE-TIME)依附其后第一个分片,
    这样删除广告分片时会连同其私有 KEY 一起删除; 内容分片若未重新声明 KEY,
    继承的最近 KEY 回到广告前的内容 KEY, 语义不变。
    #EXT-X-DISCONTINUITY 不保留原行, 发射时按 block_index 重建,
    被清空的块边界会自动坍缩。
    """
    parsed = ParsedPlaylist()
    pending: list[str] = []
    block_index = 0
    in_header = True

    for line in lines:
        if line == "#EXT-X-ENDLIST":
            parsed.is_vod = True
        if not line.startswith("#"):
            in_header = False
            extinf_line = next(
                (item for item in pending if item.startswith("#EXTINF")), None
            )
            parsed.segments.append(
                ParsedSegment(
                    uri_line=line,
                    absolute_url=resolve_uri(line),
                    duration=_parse_duration(extinf_line),
                    extinf_line=extinf_line,
                    tags=[item for item in pending if not item.startswith("#EXTINF")],
                    block_index=block_index,
                )
            )
            pending = []
            continue
        if line == "#EXT-X-DISCONTINUITY":
            in_header = False
            block_index += 1
            continue
        if line.startswith(_SEGMENT_TAG_PREFIXES):
            in_header = False
            pending.append(line)
            if line.startswith("#EXT-X-KEY"):
                parsed.has_key_tags = True
            continue
        if in_header:
            parsed.header_lines.append(line)
        else:
            # 分片区间内出现的非分片级标签(少见), 依附到下一个分片避免错位
            pending.append(line)
    parsed.trailing_lines.extend(pending)
    return parsed


def filter_segments(
    parsed: ParsedPlaylist, mode: str, playlist_url: str
) -> FilterResult:
    total = len(parsed.segments)
    if total == 0 or mode == MODE_OFF:
        return FilterResult(kept=[True] * total, removed_count=0, strategy="none")

    kept = [
        not is_ad_segment(segment.duration, segment.absolute_url)
        for segment in parsed.segments
    ]
    result = _build_result(kept, playlist_url, mode, "markers")
    if result.removed_count:
        return result
    if mode != MODE_SMART or not parsed.is_vod:
        return result

    for strategy_name, strategy in (
        ("digit", _digit_drops),
        ("length", _length_drops),
        ("stats", _stats_drops),
    ):
        drops = strategy(parsed)
        if not drops:
            continue
        if len(drops) / total > MAX_TOTAL_DROP_RATIO:
            logger.debug(
                "m3u8 ad filter: strategy=%s dropped %d/%d exceeds ratio, url=%s",
                strategy_name, len(drops), total, playlist_url,
            )
            continue
        kept = [index not in drops for index in range(total)]
        result = _build_result(kept, playlist_url, mode, strategy_name)
        if result.removed_count:
            return result
    return FilterResult(kept=[True] * total, removed_count=0, strategy="none")


def _build_result(
    kept: list[bool], playlist_url: str, mode: str, strategy: str
) -> FilterResult:
    # 永不清空: 过滤命中全部分片时视为误判, 原样保留
    if not any(kept):
        logger.warning(
            "m3u8 ad filter: strategy=%s would remove all segments, url=%s",
            strategy, playlist_url,
        )
        return FilterResult(kept=[True] * len(kept), removed_count=0, strategy="none")
    removed_count = kept.count(False)
    if not removed_count:
        return FilterResult(kept=kept, removed_count=0, strategy="none")
    _log_summary(playlist_url, mode, strategy, removed_count, len(kept))
    return FilterResult(kept=kept, removed_count=removed_count, strategy=strategy)


def _digit_drops(parsed: ParsedPlaylist) -> set[int]:
    """数字序号过滤: 序号中断且之后严格恢复(+1)的短分片串视为广告。

    任何分片串不满足"前后均为链上分片且序号严格恢复"时整体放弃,
    以拦截编号重启的多段拼接片源(参考实现的双向遍历在此场景会整段误删)。
    """
    segments = parsed.segments
    total = len(segments)
    if total < MIN_SEGMENTS:
        return set()
    numbers = [_trailing_number(segment.uri_line) for segment in segments]
    numbered_positions = [
        index for index, number in enumerate(numbers) if number is not None
    ]
    if not numbered_positions or len(numbered_positions) / total < DIGIT_NUMBERED_RATIO:
        return set()

    # O(n) 求最长严格 +1 递增链: 以数值为键记录各数值的最优链尾
    best_by_value: dict[int, tuple[int, int]] = {}
    chain_length = [0] * len(numbered_positions)
    chain_prev = [-1] * len(numbered_positions)
    for order, position in enumerate(numbered_positions):
        number = numbers[position]
        assert number is not None
        previous = best_by_value.get(number - 1)
        if previous is not None:
            chain_length[order] = chain_length[previous[0]] + 1
            chain_prev[order] = previous[0]
        else:
            chain_length[order] = 1
        current = best_by_value.get(number)
        if current is None or chain_length[order] > chain_length[current[0]]:
            best_by_value[number] = (order, position)

    best_order = max(range(len(numbered_positions)), key=chain_length.__getitem__)
    if chain_length[best_order] / len(numbered_positions) < DIGIT_CHAIN_COVERAGE:
        return set()
    on_chain = [False] * total
    order = best_order
    while order != -1:
        on_chain[numbered_positions[order]] = True
        order = chain_prev[order]

    drops: set[int] = set()
    run_start: int | None = None
    for index in range(total + 1):
        off_chain = index < total and not on_chain[index]
        if off_chain and run_start is None:
            run_start = index
            continue
        if not off_chain and run_start is not None:
            run_end = index - 1
            previous_chain = _find_on_chain_before(on_chain, run_start)
            next_chain = _find_on_chain_after(on_chain, run_end)
            resumes = False
            if previous_chain is not None and next_chain is not None:
                previous_number = numbers[previous_chain]
                next_number = numbers[next_chain]
                resumes = (
                    previous_number is not None
                    and next_number is not None
                    and next_number == previous_number + 1
                )
            if not (run_end - run_start + 1 <= MAX_AD_RUN and resumes):
                return set()
            drops.update(range(run_start, run_end + 1))
            run_start = None
    return drops


def _find_on_chain_before(on_chain: list[bool], index: int) -> int | None:
    for candidate in range(index - 1, -1, -1):
        if on_chain[candidate]:
            return candidate
    return None


def _find_on_chain_after(on_chain: list[bool], index: int) -> int | None:
    for candidate in range(index + 1, len(on_chain)):
        if on_chain[candidate]:
            return candidate
    return None


def _length_drops(parsed: ParsedPlaylist) -> set[int]:
    """命名长度过滤: 长度众数占绝对主导时, 偏离众数的短分片串视为广告。"""
    segments = parsed.segments
    total = len(segments)
    if total < MIN_SEGMENTS:
        return set()
    lengths = [len(_basename(segment.uri_line)) for segment in segments]
    benchmark, benchmark_count = Counter(lengths).most_common(1)[0]
    if benchmark_count / total < LENGTH_DOMINANCE:
        return set()

    drops: set[int] = set()
    index = 0
    while index < total:
        if lengths[index] == benchmark:
            index += 1
            continue
        run_end = index
        while run_end < total and lengths[run_end] != benchmark:
            run_end += 1
        if run_end - index <= MAX_AD_RUN:
            drops.update(range(index, run_end))
        index = run_end
    return drops


def _stats_drops(parsed: ParsedPlaylist) -> set[int]:
    """正态分布分段统计: 按 DISCONTINUITY 分块, ts 数明显低于均值的非首块视为广告块。

    首块永不删除(可能携带全局 KEY/MAP); 统计均值/标准差时同样排除首块。
    """
    segments = parsed.segments
    total = len(segments)
    if total < MIN_SEGMENTS:
        return set()
    key_uris = {
        match
        for line in parsed.header_lines
        for match in _KEY_URI_RE.findall(line)
    } | {
        match
        for segment in segments
        for tag in segment.tags
        for match in _KEY_URI_RE.findall(tag)
    }
    if len(key_uris) >= KEY_ROTATION_LIMIT:
        return set()

    blocks: dict[int, list[int]] = {}
    for index, segment in enumerate(segments):
        blocks.setdefault(segment.block_index, []).append(index)
    ordered_blocks = [blocks[key] for key in sorted(blocks)]
    if len(ordered_blocks) < STATS_MIN_BLOCKS:
        return set()

    counts = [len(block) for block in ordered_blocks[1:]]
    average = sum(counts) / len(counts)
    std_dev = math.sqrt(sum((count - average) ** 2 for count in counts) / len(counts))
    threshold = min(STATS_CAP, int(max(STATS_FLOOR, average - STATS_FACTOR * std_dev)))

    drops: set[int] = set()
    for block in ordered_blocks[1:]:
        if len(block) < threshold:
            drops.update(block)
    return drops


def _parse_duration(extinf_line: str | None) -> float | None:
    if extinf_line is None:
        return None
    try:
        return float(extinf_line.split(":", 1)[1].split(",", 1)[0])
    except (IndexError, ValueError):
        return None


def _trailing_number(uri_line: str) -> int | None:
    basename = _basename(uri_line)
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    digit_runs = _DIGIT_RUN_RE.findall(stem)
    if not digit_runs:
        return None
    try:
        return int(digit_runs[-1])
    except ValueError:
        return None


def _basename(uri_line: str) -> str:
    return urlparse(uri_line).path.rsplit("/", 1)[-1]


def _log_summary(
    playlist_url: str, mode: str, strategy: str, removed: int, total: int
) -> None:
    logger.info(
        "m3u8 ad filter: mode=%s strategy=%s removed=%d/%d url=%s",
        mode, strategy, removed, total, playlist_url,
        extra={"log_category": "network", "log_source": "app"},
    )
