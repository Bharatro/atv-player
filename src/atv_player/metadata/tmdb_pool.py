"""TMDB 访问线路轮询池。

官方 api/image 域名国内直连不通,免费 Worker 反代镜像各有每日限额,轮询分摊额度。
镜像池支持逗号/分号/空白(含全角)分隔多个地址;哨兵值 ``worker-pool`` 解析为内置
Worker 池(地址只存代码,设置值不逐个落库)。空值/非法项一律丢弃,池空即回落官方
直连,行为与历史单镜像版本一致。端口自 alist-tvbox TmdbEndpoint。

池在构造时随机打乱一次(大量客户端集中启动时流量不全砸书写顺序的第一个
Worker),之后轮询序列稳定;API 与图片各自独立计数,逐请求 round robin。
"""

from __future__ import annotations

import itertools
import random
import re
from collections.abc import Iterable
from urllib.parse import urlparse, urlunparse

WORKER_POOL_VALUE = "worker-pool"
OFFICIAL_API_BASE = "https://api.themoviedb.org"
OFFICIAL_IMAGE_BASE = "https://image.tmdb.org/t/p/"

#: 内置 Worker 轮询池(免费额度分摊);构造时洗牌,此处书写顺序无关紧要。
BUILTIN_WORKER_POOL: tuple[str, ...] = (
    "https://tmdb.power0721.workers.dev",
    "https://tmdb.swust-oj.workers.dev",
    "https://tmdb.8866033.workers.dev",
    "https://tmdb.power348045.workers.dev",
    "https://tmdb.harold348047.workers.dev",
    "https://tmdb.ai-09b.workers.dev",
    "https://tmdb.root-df0.workers.dev",
    "https://tmdb.atv-8c1.workers.dev",
    "https://tmdb.odd-math-a42b.workers.dev",
    "https://tmdb.test-d2c.workers.dev",
    "https://tmdb.code-a96.workers.dev",
    "https://tmdb.claude-b79.workers.dev",
)

_POOL_SEPARATOR = re.compile(r"[,，;；\s]+")


def normalize_mirror_host(value: object) -> str:
    """单项镜像地址归一:剥尾斜杠与 /3、/t/p 路径尾巴;非 http(s) 返回空串。"""
    host = str(value or "").strip()
    while host.endswith("/"):
        host = host[:-1]
    for suffix in ("/t/p", "/3"):
        if host.endswith(suffix):
            host = host[: -len(suffix)]
            break
    if not host:
        return ""
    parsed = urlparse(host)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def parse_mirror_pool(value: object) -> list[str]:
    """拆镜像池:哨兵值展开内置池;否则按分隔符拆分,逐项归一,丢弃空项/非法项/重复项。"""
    text = str(value or "").strip()
    if not text:
        return []
    if text == WORKER_POOL_VALUE:
        return list(BUILTIN_WORKER_POOL)
    pool: list[str] = []
    for item in _POOL_SEPARATOR.split(text):
        host = normalize_mirror_host(item)
        if host and host not in pool:
            pool.append(host)
    return pool


def canonicalize_mirror_value(value: object) -> str:
    """设置存储用归一:空→空串,哨兵值原样,其余解析为去重后的逗号串(全非法→空串)。"""
    text = str(value or "").strip()
    if not text or text == WORKER_POOL_VALUE:
        return text
    return ",".join(parse_mirror_pool(text))


class TmdbMirrorPool:
    """镜像轮询池:构造时洗牌、逐请求 round robin;池空等价官方直连。"""

    def __init__(self, hosts: Iterable[str] = ()) -> None:
        self._hosts: list[str] = list(hosts)
        random.shuffle(self._hosts)
        self._api_counter = itertools.count()
        self._image_counter = itertools.count()

    def __bool__(self) -> bool:
        return bool(self._hosts)

    def __len__(self) -> int:
        return len(self._hosts)

    @property
    def hosts(self) -> tuple[str, ...]:
        return tuple(self._hosts)

    def next_api_base(self) -> str:
        """API base(不带 /3);空池回落官方。"""
        return self._rotate(self._hosts, self._api_counter, OFFICIAL_API_BASE)

    def next_image_base(self) -> str | None:
        """图片镜像 base(不含 /t/p 路径);无可用镜像返回 None=不重写(官方直连)。
        显式配官方 API 不构成镜像线路(官方图床本来就是要绕开的对象)。"""
        mirrors = [host for host in self._hosts if host != OFFICIAL_API_BASE]
        return self._rotate(mirrors, self._image_counter, None)

    @staticmethod
    def _rotate(hosts: list[str], counter: itertools.count, fallback: str | None) -> str | None:
        if not hosts:
            return fallback
        if len(hosts) == 1:
            return hosts[0]
        return hosts[next(counter) % len(hosts)]


def build_mirror_pool(value: object) -> TmdbMirrorPool:
    return TmdbMirrorPool(parse_mirror_pool(value))
