"""章节自动跳过:根据章节标题识别片头/片尾并计算跳转目标。

章节来源两类:B站 view_points 下发的 PlayChapter(带 end_seconds)与 mpv
内嵌章节(仅 start,end 由次章起点/总时长推得)。识别只看标题与时长结构,
不做网络请求;用户确认横幅与进度记录由调用方(PlayerWindow)负责。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# 命中片头:中文子串直配;拉丁词锚定开头/结尾(CJK 后接 op/ed 无 \b 边界,用负向后行)。
_INTRO_TITLE_RE = re.compile(
    r"片头|片頭|开场|開場|intro|opening|^\s*op\s*\d*\s*$|(?<![a-z])op\s*$",
    re.IGNORECASE,
)
# 命中片尾:片尾/结尾/Credits/ED/Ending 等。
_OUTRO_TITLE_RE = re.compile(
    r"片尾|谢幕|結尾|结尾|credits?\b|outro|^\s*ed\s*\d*\s*$|(?<![a-z])ed\s*$|\bending\b",
    re.IGNORECASE,
)
# 片后内容:即便含"片尾/Credits"字样也不算片尾(如"片尾彩蛋")。
_POST_CREDIT_TITLE_RE = re.compile(
    r"彩蛋|post.?credits?|after.?credits?|stinger",
    re.IGNORECASE,
)
# 前置广告:标题直说(也可无标注,靠"首章极短+次章片头"结构推断)。
_AD_TITLE_RE = re.compile(
    r"广告|廣告|^\s*ad\s*\d*\s*$|promo|赞助|贊助|推广",
    re.IGNORECASE,
)

# 首章视为前置广告的最大时长:用户场景是"十几秒正片(实为广告)+ 几十秒片头"。
AD_MAX_SECONDS = 30.0
# 首章明确标注广告时放宽到的最大时长(信任标题)。
EXPLICIT_AD_MAX_SECONDS = 90.0
# 终点领先当前位置不足该值不值得跳。
MIN_SKIP_SECONDS = 5.0
# 跳过后剩余正片不足该值不跳(防止把结尾整段跳掉)。
MIN_REMAIN_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class SkipChapter:
    title: str
    start_seconds: float
    end_seconds: float


def is_intro_title(title: str) -> bool:
    return bool(_INTRO_TITLE_RE.search(str(title or "").strip()))


def is_outro_title(title: str) -> bool:
    text = str(title or "").strip()
    if _POST_CREDIT_TITLE_RE.search(text):
        return False
    return bool(_OUTRO_TITLE_RE.search(text))


def is_ad_title(title: str) -> bool:
    return bool(_AD_TITLE_RE.search(str(title or "").strip()))


def normalize_chapters(
    entries: Iterable[object], duration_seconds: float
) -> list[SkipChapter]:
    """把 PlayChapter / mpv Chapter 统一为带 end 的 SkipChapter。

    end 依次取:显式 end_seconds、次章 start、总时长(未知则为 0,由调用方
    的剩余时长护栏兜底)。
    """
    raw: list[tuple[str, float, float]] = []
    for entry in entries:
        title = str(getattr(entry, "title", "") or "").strip()
        start = max(0.0, float(getattr(entry, "start_seconds", 0.0) or 0.0))
        end = float(getattr(entry, "end_seconds", 0.0) or 0.0)
        raw.append((title, start, end))
    raw.sort(key=lambda item: item[1])
    duration = max(0.0, float(duration_seconds or 0.0))
    chapters: list[SkipChapter] = []
    for index, (title, start, end) in enumerate(raw):
        if end <= start:
            end = raw[index + 1][1] if index + 1 < len(raw) else duration
        chapters.append(
            SkipChapter(title=title, start_seconds=start, end_seconds=max(end, start))
        )
    return chapters


def chapter_index_at(chapters: Sequence[SkipChapter], seconds: float) -> int | None:
    matched: int | None = None
    for index, chapter in enumerate(chapters):
        if chapter.start_seconds > seconds:
            break
        matched = index
    return matched


def intro_skip_target(
    chapters: Sequence[SkipChapter],
    *,
    position_seconds: float,
    duration_seconds: float,
) -> float | None:
    """起播时计算片头直跳终点;None 表示不跳。

    支持三种形态:
    1. 首章即片头(OP/片头/Intro...)→ 跳到首章末尾;
    2. 首章极短或标注广告、次章为片头(十几秒"正片"广告 + 几十秒片头)→ 跳到次章末尾;
    3. 首章明确标注广告、次章非片头 → 跳到次章开头。

    首章既非片头也非广告时(如 3 分钟冷开场后接 OP)不跳,避免误吞正片。
    """
    if not chapters:
        return None
    first = chapters[0]
    first_span = first.end_seconds - first.start_seconds
    looks_like_ad = first_span <= AD_MAX_SECONDS or (
        is_ad_title(first.title) and first_span <= EXPLICIT_AD_MAX_SECONDS
    )
    target: float | None = None
    if is_intro_title(first.title):
        target = first.end_seconds
    elif len(chapters) >= 2 and first.start_seconds <= 5.0 and looks_like_ad:
        second = chapters[1]
        if is_intro_title(second.title):
            target = second.end_seconds
        else:
            target = second.start_seconds
    if target is None:
        return None
    if position_seconds >= target - MIN_SKIP_SECONDS:
        return None
    if duration_seconds > 0 and duration_seconds - target < MIN_REMAIN_SECONDS:
        return None
    return target


@dataclass(frozen=True, slots=True)
class OutroSkip:
    chapter: SkipChapter
    chapter_index: int
    is_last: bool
    # 非末章:片尾后下一章(彩蛋/下集预告等)的起点;末章为 None。
    next_start_seconds: float | None


def outro_skip_target(
    chapters: Sequence[SkipChapter],
    *,
    position_seconds: float,
) -> OutroSkip | None:
    """position 所在章节若为片尾且位于尾部两章内,返回跳过判定。

    只认尾部两章,避免"片尾花絮"之类中途同名章节误触发;调用方据 is_last
    决定走片尾倒计时切集还是跳到下一章。
    """
    index = chapter_index_at(chapters, position_seconds)
    if index is None or not is_outro_title(chapters[index].title):
        return None
    if index < len(chapters) - 2:
        return None
    is_last = index == len(chapters) - 1
    return OutroSkip(
        chapter=chapters[index],
        chapter_index=index,
        is_last=is_last,
        next_start_seconds=None if is_last else chapters[index + 1].start_seconds,
    )
