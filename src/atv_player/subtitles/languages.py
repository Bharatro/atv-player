"""字幕语言归一与优先级。

排序口径与 player/mpv_widget.py 的 ``_chinese_subtitle_preference`` 保持一致
（那边是"越大越优先"，这里统一成"越小越优先"以便直接用于 sort key）：

    简英双语 > 繁英/中英双语 > 简体 > 通用中文 > 繁体 > 英文 > 其他
"""

from __future__ import annotations

CHS_ENG = "chs_eng"
CHT_ENG = "cht_eng"
ZH_ENG = "zh_eng"
CHS = "chs"
ZH = "zh"
CHT = "cht"
ENG = "eng"
OTHER = "other"

_LANGUAGE_LABELS = {
    CHS_ENG: "简英双语",
    CHT_ENG: "繁英双语",
    ZH_ENG: "中英双语",
    CHS: "简体中文",
    ZH: "中文",
    CHT: "繁体中文",
    ENG: "English",
    OTHER: "其他",
}

# 越小越优先。简英双语最高。
_LANGUAGE_RANKS = {
    CHS_ENG: 0,
    CHT_ENG: 1,
    ZH_ENG: 1,
    CHS: 2,
    ZH: 3,
    CHT: 4,
    ENG: 5,
    OTHER: 6,
}

_ENGLISH_TOKENS = ("english", "eng", "英文", "英语", "英", "en")
_SIMPLIFIED_TOKENS = (
    "简英", "简中", "简体", "简", "chs", "hans", "simplified", "gb", "sc",
    "zh-cn", "zh_cn",
)
_TRADITIONAL_TOKENS = (
    "繁英", "繁中", "繁體", "繁体", "繁", "cht", "hant", "big5", "traditional",
    "tranditional", "tc", "zh-tw", "zh_tw", "zh-hk",
)
_CHINESE_TOKENS = ("中文", "中字", "双语", "chinese", "chi", "zho", "zh")


def normalize_language(*hints: str) -> str:
    """把站点给的语言描述/文件名归一成语言代码。

    ``hints`` 按可信度从高到低传入（如 lang 字段、字幕名、文件名）。
    """
    text = " ".join(str(hint or "") for hint in hints).casefold()
    if not text.strip():
        return OTHER
    has_english = any(token in text for token in _ENGLISH_TOKENS)
    has_simplified = any(token in text for token in _SIMPLIFIED_TOKENS)
    has_traditional = any(token in text for token in _TRADITIONAL_TOKENS)
    has_chinese = has_simplified or has_traditional or any(
        token in text for token in _CHINESE_TOKENS
    )
    if has_english and has_chinese:
        if has_simplified:
            return CHS_ENG
        if has_traditional:
            return CHT_ENG
        return ZH_ENG
    if has_simplified:
        return CHS
    if has_traditional:
        return CHT
    if has_chinese:
        return ZH
    if has_english:
        return ENG
    return OTHER


def language_label(code: str) -> str:
    return _LANGUAGE_LABELS.get(code, _LANGUAGE_LABELS[OTHER])


def language_rank(code: str) -> int:
    return _LANGUAGE_RANKS.get(code, _LANGUAGE_RANKS[OTHER])
