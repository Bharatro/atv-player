from atv_player.metadata.providers.bangumi import BangumiMetadataProvider
from atv_player.metadata.providers.bilibili import BilibiliMetadataProvider
from atv_player.metadata.providers.douban import DoubanProvider
from atv_player.metadata.providers.iqiyi import IqiyiMetadataProvider
from atv_player.metadata.providers.local_douban import LocalDoubanProvider
from atv_player.metadata.providers.migu import MiguMetadataProvider
from atv_player.metadata.providers.official_douban import OfficialDoubanProvider
from atv_player.metadata.providers.plugin import CustomPluginProvider
from atv_player.metadata.providers.sohu import SohuMetadataProvider
from atv_player.metadata.providers.tencent import TencentMetadataProvider
from atv_player.metadata.providers.tmdb import TMDBProvider
from atv_player.metadata.providers.youku import YoukuMetadataProvider

__all__ = [
    "BangumiMetadataProvider",
    "BilibiliMetadataProvider",
    "CustomPluginProvider",
    "DoubanProvider",
    "IqiyiMetadataProvider",
    "MiguMetadataProvider",
    "OfficialDoubanProvider",
    "LocalDoubanProvider",
    "SohuMetadataProvider",
    "TencentMetadataProvider",
    "TMDBProvider",
    "YoukuMetadataProvider",
]
