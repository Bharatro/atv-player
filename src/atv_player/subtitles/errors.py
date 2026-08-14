class SubtitleError(Exception):
    pass


class SubtitleProviderError(SubtitleError):
    """字幕站返回了错误，或页面结构与预期不符。"""


class SubtitleTokenMissingError(SubtitleProviderError):
    """该站需要 token / API Key，但用户尚未配置。"""


class SubtitleBlockedError(SubtitleProviderError):
    """被验证码或风控拦截（抓取站常见）。"""


class SubtitleQuotaExceededError(SubtitleProviderError):
    """超出站点配额（如 OpenSubtitles 免费层每日下载上限）。"""


class SubtitleEmptyResultError(SubtitleError):
    pass


class SubtitleArchiveError(SubtitleError):
    pass


class SubtitleArchiveUnsupportedError(SubtitleArchiveError):
    """压缩格式标准库无法解开（主要是 rar）。"""
