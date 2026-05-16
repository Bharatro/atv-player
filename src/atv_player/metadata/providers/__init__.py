from atv_player.metadata.providers.bilibili import BilibiliMetadataProvider
from atv_player.metadata.providers.douban import DoubanProvider
from atv_player.metadata.providers.iqiyi import IqiyiMetadataProvider
from atv_player.metadata.providers.local_douban import OfficialDoubanProvider
from atv_player.metadata.providers.plugin import CustomPluginProvider
from atv_player.metadata.providers.remote_douban import LocalDoubanProvider
from atv_player.metadata.providers.tencent import TencentMetadataProvider
from atv_player.metadata.providers.tmdb import TMDBProvider

__all__ = [
    "BilibiliMetadataProvider",
    "CustomPluginProvider",
    "DoubanProvider",
    "IqiyiMetadataProvider",
    "OfficialDoubanProvider",
    "LocalDoubanProvider",
    "TencentMetadataProvider",
    "TMDBProvider",
]
