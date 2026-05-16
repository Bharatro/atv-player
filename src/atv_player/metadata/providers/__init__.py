from atv_player.metadata.providers.douban import DoubanProvider
from atv_player.metadata.providers.local_douban import LocalDoubanProvider
from atv_player.metadata.providers.plugin import CustomPluginProvider
from atv_player.metadata.providers.remote_douban import RemoteDoubanProvider
from atv_player.metadata.providers.tmdb import TMDBProvider

__all__ = [
    "CustomPluginProvider",
    "DoubanProvider",
    "LocalDoubanProvider",
    "RemoteDoubanProvider",
    "TMDBProvider",
]
