"""chapter_skip 纯逻辑:片头/片尾识别与跳转目标计算。"""

from __future__ import annotations

from collections.abc import Sequence

from atv_player.chapter_skip import (
    SkipChapter,
    intro_skip_target,
    is_ad_title,
    is_intro_title,
    is_outro_title,
    normalize_chapters,
    outro_skip_target,
)
from atv_player.models import PlayChapter


def _mk(*entries: tuple[str, float, float]) -> list[PlayChapter]:
    """(标题, start, end) 三元组批量建 PlayChapter。"""
    return [
        PlayChapter(title=title, start_seconds=start, end_seconds=end)
        for title, start, end in entries
    ]


def _intro(
    entries: Sequence[tuple[str, float, float]], duration: float, position: float = 0.0
):
    return intro_skip_target(
        normalize_chapters(_mk(*entries), duration),
        position_seconds=position,
        duration_seconds=duration,
    )


class TestTitlePatterns:
    def test_intro_titles(self) -> None:
        titles = ("片头", "片头OP", "开场", "Intro", "opening", "OP",
                  "op 1", "OP1", "本集op")
        for title in titles:
            assert is_intro_title(title), title

    def test_intro_titles_reject_lookalikes(self) -> None:
        for title in ("Loop", "Opera", "Option", "正片", "Drop Dead", "片尾"):
            assert not is_intro_title(title), title

    def test_outro_titles(self) -> None:
        titles = ("片尾", "片尾曲", "End Credits", "credits",
                  "Credit", "ED", "ED2", "ending")
        for title in titles:
            assert is_outro_title(title), title

    def test_post_credit_titles_are_not_outro(self) -> None:
        titles = ("片尾彩蛋", "彩蛋", "Post-Credits Scene",
                  "after credits", "stinger")
        for title in titles:
            assert not is_outro_title(title), title

    def test_ad_titles(self) -> None:
        for title in ("广告", "赞助商广告", "AD", "ad 2", "promo", "推广"):
            assert is_ad_title(title), title


class TestNormalizeChapters:
    def test_play_chapter_with_explicit_end(self) -> None:
        chapters = normalize_chapters(
            _mk(("片头", 0.0, 90.0), ("正片", 90.0, 3600.0)), 3600.0
        )
        assert [(c.title, c.start_seconds, c.end_seconds) for c in chapters] == [
            ("片头", 0.0, 90.0),
            ("正片", 90.0, 3600.0),
        ]

    def test_end_falls_back_to_next_start_then_duration(self) -> None:
        class MpvChapter:
            def __init__(self, title: str, start: float) -> None:
                self.title = title
                self.start_seconds = start

        chapters = normalize_chapters(
            [MpvChapter("正片", 0.0), MpvChapter("End Credits", 3000.0)], 3300.0
        )
        assert chapters[0].end_seconds == 3000.0
        assert chapters[1].end_seconds == 3300.0


class TestIntroSkipTarget:
    def test_first_chapter_intro_skips_to_its_end(self) -> None:
        assert _intro((("片头", 0.0, 90.0), ("正片", 90.0, 3600.0)), 3600.0) == 90.0

    def test_short_ad_then_intro_compound_structure(self) -> None:
        """十几秒"正片"(实为广告)+ 几十秒片头 → 直跳片头末尾。"""
        assert (
            _intro(
                (("正片", 0.0, 15.0), ("片头", 15.0, 105.0),
                 ("正片", 105.0, 2400.0)),
                2400.0,
            )
            == 105.0
        )

    def test_cold_open_then_op_is_not_skipped(self) -> None:
        """3 分钟冷开场后接 OP:首章既非片头也非广告,不跳。"""
        assert (
            _intro(
                (("正片", 0.0, 180.0), ("OP", 180.0, 270.0),
                 ("正片", 270.0, 2400.0)),
                2400.0,
            )
            is None
        )

    def test_explicit_ad_title_skips_to_next_chapter(self) -> None:
        assert _intro((("广告", 0.0, 45.0), ("正片", 45.0, 2400.0)), 2400.0) == 45.0

    def test_resume_past_intro_does_not_skip(self) -> None:
        entries = (("片头", 0.0, 90.0), ("正片", 90.0, 3600.0))
        assert _intro(entries, 3600.0, position=600.0) is None

    def test_target_too_close_to_current_position_rejected(self) -> None:
        # 终点只领先当前位置 4s(<MIN_SKIP 5s):不跳。
        entries = (("片头", 0.0, 90.0), ("正片", 90.0, 3600.0))
        assert _intro(entries, 3600.0, position=86.0) is None

    def test_target_leaves_no_real_content_rejected(self) -> None:
        assert _intro((("片头", 0.0, 90.0), ("正片", 90.0, 100.0)), 100.0) is None

    def test_no_chapters_returns_none(self) -> None:
        assert _intro((), 3600.0) is None

    def test_neither_intro_nor_ad_first_chapter_returns_none(self) -> None:
        entries = (("第一幕", 0.0, 600.0), ("第二幕", 600.0, 2400.0))
        assert _intro(entries, 2400.0) is None


class TestOutroSkipTarget:
    def _outro(
        self,
        entries: Sequence[tuple[str, float, float]],
        position: float,
        duration: float,
    ):
        return outro_skip_target(
            normalize_chapters(_mk(*entries), duration), position_seconds=position
        )

    def test_last_outro_chapter_detected(self) -> None:
        skip = self._outro(
            (("正片", 0.0, 2280.0), ("End Credits", 2280.0, 2400.0)), 2300.0, 2400.0
        )
        assert skip is not None
        assert skip.is_last is True
        assert skip.next_start_seconds is None
        assert skip.chapter.title == "End Credits"

    def test_second_to_last_outro_targets_next_chapter(self) -> None:
        entries = (("正片", 0.0, 2200.0), ("片尾", 2200.0, 2300.0),
                   ("彩蛋", 2300.0, 2400.0))
        skip = self._outro(entries, 2210.0, 2400.0)
        assert skip is not None
        assert skip.is_last is False
        assert skip.next_start_seconds == 2300.0

    def test_mid_video_outro_ignored(self) -> None:
        """中途"片尾花絮"同名章节不触发(只认尾部两章)。"""
        entries = (
            ("正片", 0.0, 100.0),
            ("片尾花絮", 100.0, 200.0),
            ("正片", 200.0, 2280.0),
            ("片尾", 2280.0, 2400.0),
        )
        assert self._outro(entries, 150.0, 2400.0) is None
        assert self._outro(entries, 2300.0, 2400.0) is not None

    def test_position_in_main_content_returns_none(self) -> None:
        entries = (("正片", 0.0, 2280.0), ("片尾", 2280.0, 2400.0))
        assert self._outro(entries, 1000.0, 2400.0) is None

    def test_post_credit_last_chapter_not_treated_as_outro(self) -> None:
        entries = (
            ("正片", 0.0, 2200.0),
            ("片尾", 2200.0, 2300.0),
            ("片尾彩蛋", 2300.0, 2400.0),
        )
        skip = self._outro(entries, 2350.0, 2400.0)
        assert skip is None


class TestSkipChapterDataclass:
    def test_frozen(self) -> None:
        chapter = SkipChapter(title="片头", start_seconds=0.0, end_seconds=90.0)
        try:
            chapter.title = "x"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("SkipChapter should be frozen")
