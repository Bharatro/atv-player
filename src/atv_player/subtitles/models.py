from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SubtitleQuery:
    """一次字幕搜索请求。

    ``title`` / ``season`` / ``episode`` 等字段通常由 release_parser 从视频文件名
    解析而来；``imdb_id`` / ``tmdb_id`` 若能从已有元数据拿到则优先使用，命中率
    远高于按片名搜索。
    """

    title: str = ""
    episode: int | None = None
    season: int | None = None
    year: int = 0
    imdb_id: str = ""
    tmdb_id: str = ""
    file_name: str = ""
    # 以下由发布名解析得到，用于匹配打分
    resolution: str = ""
    source: str = ""
    codec: str = ""
    release_group: str = ""

    @property
    def has_media_id(self) -> bool:
        return bool(self.imdb_id or self.tmdb_id)

    @property
    def is_episode(self) -> bool:
        return self.episode is not None


@dataclass(frozen=True, slots=True)
class SubtitleSearchItem:
    provider: str
    provider_label: str
    subtitle_id: str
    name: str
    language: str = "other"
    language_label: str = ""
    format: str = ""
    release_site: str = ""
    release_name: str = ""
    download_count: int = 0
    vote_score: float = 0.0
    season: int | None = None
    episode: int | None = None
    hearing_impaired: bool = False
    forced: bool = False
    url: str = ""
    # 匹配打分结果，由 matcher 填充
    score: int = 0
    match_percent: int = 0
    # 下载该条字幕所需的额外上下文（各 provider 自定义，如详情页地址）
    context: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SubtitleProviderGroup:
    provider: str
    provider_label: str
    items: list[SubtitleSearchItem]
    # 站点要求的署名等提示文案（如 ASSRT 的"字幕服务由 assrt.net 提供"）
    notice: str = ""


@dataclass(frozen=True, slots=True)
class SubtitleSearchResult:
    groups: list[SubtitleProviderGroup] = field(default_factory=list)
    # provider id -> 失败原因，用于在界面上区分"没搜到"和"这个站挂了"
    errors: dict[str, str] = field(default_factory=dict)
    # 未配置 token 而被跳过的站点 id
    skipped: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(len(group.items) for group in self.groups)

    def best_item(self) -> SubtitleSearchItem | None:
        best: SubtitleSearchItem | None = None
        for group in self.groups:
            for item in group.items:
                if best is None or item.score > best.score:
                    best = item
        return best


@dataclass(frozen=True, slots=True)
class SubtitleContent:
    """下载并解包后的字幕正文。"""

    text: str
    suffix: str
    name: str = ""
