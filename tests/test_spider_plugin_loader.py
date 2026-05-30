import logging
from pathlib import Path

import httpx
import pytest

from atv_player.models import SpiderPluginConfig
from atv_player.network_proxy import ProxyConfig, ProxyDecider
from atv_player.plugins.loader import SpiderPluginLoader
from atv_player.plugins.compat.base.spider import Spider, set_proxy_decider_loader
from tests.secspider_fixtures import build_secspider_package

PLUGIN_SOURCE = """
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.extend = extend

    def getName(self):
        return "红果短剧"

    def homeContent(self, filter):
        return {
            "class": [{"type_id": "hot", "type_name": "热门"}],
            "list": [{"vod_id": "/detail/1", "vod_name": "短剧 1"}],
        }
"""


def test_loader_loads_local_plugin_and_installs_base_spider_alias(tmp_path: Path) -> None:
    plugin_path = tmp_path / "红果短剧.py"
    plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=1,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config)

    assert loaded.plugin_name == "红果短剧"
    assert loaded.spider.homeContent(False)["class"][0]["type_name"] == "热门"
    assert loaded.search_enabled is False


def test_loader_can_defer_plugin_init_until_explicit_initialization(tmp_path: Path) -> None:
    plugin_path = tmp_path / "懒加载插件.py"
    plugin_path.write_text(
        """
from base.spider import Spider

class Spider(Spider):
    init_calls = 0

    def init(self, extend=""):
        type(self).init_calls += 1
        self.extend = extend

    def getName(self):
        return "懒加载插件"
""".strip(),
        encoding="utf-8",
    )
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=101,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
        config_text="hello",
    )

    loaded = loader.load(config, initialize=False)

    assert loaded.plugin_name == "懒加载插件"
    assert type(loaded.spider).init_calls == 0
    assert getattr(loaded.spider, "extend", "") != "hello"

    assert loaded.initialize_spider is not None
    loaded.initialize_spider()
    loaded.initialize_spider()

    assert type(loaded.spider).init_calls == 1
    assert loaded.spider.extend == "hello"


def test_loader_downloads_remote_plugin_and_reuses_cached_file_on_refresh_failure(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        calls.append(f"{url}|follow_redirects={follow_redirects}")
        if len(calls) == 1:
            return httpx.Response(200, text=PLUGIN_SOURCE)
        raise httpx.ConnectError("network down")

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get)
    config = SpiderPluginConfig(
        id=7,
        source_type="remote",
        source_value="https://example.com/红果短剧.py",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    first = loader.load(config, force_refresh=True)
    second = loader.load(first.config, force_refresh=True)

    assert first.plugin_name == "红果短剧"
    assert second.plugin_name == "红果短剧"
    assert calls == [
        "https://example.com/红果短剧.py|follow_redirects=True",
        "https://example.com/红果短剧.py|follow_redirects=True",
    ]


def test_loader_resolves_one_indirect_remote_url_before_loading_plugin(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        calls.append(url)
        if url == "https://example.com/plugin.txt":
            return httpx.Response(200, text="\nhttps://cdn.example.com/real-plugin.py\n")
        if url == "https://cdn.example.com/real-plugin.py":
            return httpx.Response(200, text=PLUGIN_SOURCE)
        raise AssertionError(f"Unexpected URL: {url}")

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get)
    config = SpiderPluginConfig(
        id=41,
        source_type="remote",
        source_value="https://example.com/plugin.txt",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "红果短剧"
    assert calls == [
        "https://example.com/plugin.txt",
        "https://cdn.example.com/real-plugin.py",
    ]
    assert "class Spider(Spider):" in Path(loaded.config.cached_file_path).read_text(encoding="utf-8")


def test_loader_fetch_remote_text_passes_proxy_kwargs(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_get(url: str, **kwargs) -> httpx.Response:
        seen.update({key: value for key, value in kwargs.items() if key in {"proxy", "trust_env"}})
        return httpx.Response(200, text=PLUGIN_SOURCE, request=httpx.Request("GET", url))

    loader = SpiderPluginLoader(
        cache_dir=tmp_path / "cache",
        get=fake_get,
        proxy_decider=ProxyDecider(
            ProxyConfig(mode="http", proxy_url="http://127.0.0.1:7890", bypass_rules=[])
        ),
    )
    config = SpiderPluginConfig(
        id=43,
        source_type="remote",
        source_value="https://example.com/plugin.py",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "红果短剧"
    assert seen["proxy"] == "http://127.0.0.1:7890"
    assert seen["trust_env"] is False


def test_compat_spider_fetch_uses_dynamic_proxy_loader(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeResponse:
        content = b"ok"
        encoding = ""

        def close(self) -> None:
            return None

    def fake_get(url: str, **kwargs) -> FakeResponse:
        seen["url"] = url
        seen["proxies"] = kwargs.get("proxies")
        return FakeResponse()

    monkeypatch.setattr("atv_player.plugins.compat.base.spider.requests.get", fake_get)
    set_proxy_decider_loader(
        lambda: ProxyDecider(
            ProxyConfig(mode="http", proxy_url="http://127.0.0.1:7890", bypass_rules=[])
        )
    )
    try:
        response = Spider().fetch("https://example.com/data.json")
    finally:
        set_proxy_decider_loader(None)

    assert response.content == b"ok"
    assert seen["url"] == "https://example.com/data.json"
    assert seen["proxies"] == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_compat_spider_post_bypasses_proxy_when_rule_matches(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeResponse:
        content = b"ok"
        encoding = ""

        def close(self) -> None:
            return None

    def fake_post(url: str, **kwargs) -> FakeResponse:
        seen["url"] = url
        seen["proxies"] = kwargs.get("proxies")
        return FakeResponse()

    monkeypatch.setattr("atv_player.plugins.compat.base.spider.requests.post", fake_post)
    set_proxy_decider_loader(
        lambda: ProxyDecider(
            ProxyConfig(
                mode="socks5",
                proxy_url="socks5://127.0.0.1:1080",
                bypass_rules=["api.example.com"],
            )
        )
    )
    try:
        response = Spider().post("https://api.example.com/update", json={"ok": True})
    finally:
        set_proxy_decider_loader(None)

    assert response.content == b"ok"
    assert seen["url"] == "https://api.example.com/update"
    assert seen["proxies"] == {"http": None, "https": None}


def test_loader_treats_python_text_as_source_instead_of_indirect_url(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        calls.append(url)
        return httpx.Response(200, text=PLUGIN_SOURCE)

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get)
    config = SpiderPluginConfig(
        id=42,
        source_type="remote",
        source_value="https://example.com/direct.py",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "红果短剧"
    assert calls == ["https://example.com/direct.py"]


def test_loader_reuses_cached_plugin_when_indirect_second_fetch_fails(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        calls.append(url)
        if url == "https://example.com/plugin.txt":
            return httpx.Response(200, text="https://cdn.example.com/real-plugin.py")
        if url == "https://cdn.example.com/real-plugin.py":
            if len(calls) == 2:
                return httpx.Response(200, text=PLUGIN_SOURCE)
            raise httpx.ConnectError("cdn down")
        raise AssertionError(f"Unexpected URL: {url}")

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get)
    config = SpiderPluginConfig(
        id=43,
        source_type="remote",
        source_value="https://example.com/plugin.txt",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    first = loader.load(config, force_refresh=True)
    second = loader.load(first.config, force_refresh=True)

    assert first.plugin_name == "红果短剧"
    assert second.plugin_name == "红果短剧"
    assert calls == [
        "https://example.com/plugin.txt",
        "https://cdn.example.com/real-plugin.py",
        "https://example.com/plugin.txt",
        "https://cdn.example.com/real-plugin.py",
    ]


def test_loader_reports_missing_spider_class(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.py"
    bad_path.write_text("class NotSpider:\n    pass\n", encoding="utf-8")
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=2,
        source_type="local",
        source_value=str(bad_path),
        display_name="坏插件",
        enabled=True,
        sort_order=0,
    )

    with pytest.raises(ValueError, match="缺少 Spider 类"):
        loader.load(config)


def test_loader_supports_plugins_that_use_cache_during_init(tmp_path: Path) -> None:
    plugin_path = tmp_path / "cache_plugin.py"
    plugin_path.write_text(
        """
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        device_id = self.getCache("did")
        if not device_id:
            self.setCache("did", "device-1")
            device_id = self.getCache("did")
        self.device_id = device_id

    def getName(self):
        return f"缓存:{self.device_id}"
""",
        encoding="utf-8",
    )
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=3,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config)

    assert loaded.plugin_name == "缓存:device-1"


def test_loader_follows_redirects_for_remote_plugin_download(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        calls.append((url, follow_redirects))
        if follow_redirects:
            return httpx.Response(200, text=PLUGIN_SOURCE)
        return httpx.Response(302, headers={"Location": "https://cdn.example.com/spider.py"}, text="")

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get)
    config = SpiderPluginConfig(
        id=11,
        source_type="remote",
        source_value="https://example.com/redirect.py",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "红果短剧"
    assert calls == [("https://example.com/redirect.py", True)]


def test_loader_ignores_empty_cached_remote_file_and_redownloads(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_file = cache_dir / "plugin_12.py"
    cached_file.write_text("", encoding="utf-8")
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        calls.append(url)
        return httpx.Response(200, text=PLUGIN_SOURCE)

    loader = SpiderPluginLoader(cache_dir=cache_dir, get=fake_get)
    config = SpiderPluginConfig(
        id=12,
        source_type="remote",
        source_value="https://example.com/reload.py",
        display_name="",
        enabled=True,
        sort_order=0,
        cached_file_path=str(cached_file),
    )

    loaded = loader.load(config)

    assert loaded.plugin_name == "红果短剧"
    assert calls == ["https://example.com/reload.py"]
    assert "class Spider(Spider):" in cached_file.read_text(encoding="utf-8")


def test_loader_does_not_fallback_to_empty_cached_remote_file_when_refresh_fails(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_file = cache_dir / "plugin_13.py"
    cached_file.write_text("", encoding="utf-8")

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        raise httpx.ConnectError("network down")

    loader = SpiderPluginLoader(cache_dir=cache_dir, get=fake_get)
    config = SpiderPluginConfig(
        id=13,
        source_type="remote",
        source_value="https://example.com/fail.py",
        display_name="",
        enabled=True,
        sort_order=0,
        cached_file_path=str(cached_file),
    )

    with pytest.raises(httpx.ConnectError, match="network down"):
        loader.load(config, force_refresh=True)


def test_loader_passes_saved_config_text_into_spider_init(tmp_path: Path) -> None:
    plugin_path = tmp_path / "config_plugin.py"
    plugin_path.write_text(
        """
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.extend = extend

    def getName(self):
        return self.extend
""",
        encoding="utf-8",
    )
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=21,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
        config_text="site=https://example.com\ncookie=abc",
    )

    loaded = loader.load(config)

    assert loaded.plugin_name == "site=https://example.com\ncookie=abc"
    assert loaded.config.config_text == "site=https://example.com\ncookie=abc"


def test_loader_logs_loaded_plugin(tmp_path: Path, caplog) -> None:
    plugin_path = tmp_path / "红果短剧.py"
    plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=31,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
    )

    with caplog.at_level(logging.INFO):
        loaded = loader.load(config)

    assert loaded.plugin_name == "红果短剧"
    assert "Loaded spider plugin" in caplog.text
    assert "红果短剧" in caplog.text


def test_loader_loads_local_secspider_plugin(tmp_path: Path) -> None:
    package_text, keyring = build_secspider_package(
        """
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.extend = extend

    def getName(self):
        return f"加密:{self.extend}"
""",
        name="红果短剧",
    )
    plugin_path = tmp_path / "encrypted_plugin.py"
    plugin_path.write_text(package_text, encoding="utf-8")
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", keyring=keyring)
    config = SpiderPluginConfig(
        id=41,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
        config_text="site=https://example.com",
    )

    loaded = loader.load(config)

    assert loaded.plugin_name == "加密:site=https://example.com"


JS_PLUGIN_SOURCE = """
export default {
  getName() { return "JS短剧" },
  home() { return { class: [], list: [] } },
  category() { return { list: [], total: 0 } },
  detail(id) { return { list: [{ vod_id: id, vod_name: "详情", vod_play_from: "默认", vod_play_url: "正片$https://media.example/a.m3u8" }] } },
  play(flag, id) { return { parse: 0, url: id } }
}
"""

T4_PLUGIN_SOURCE = """
const axios = require("axios");

const META = { name: "酷我听书", api: "/video/KuWoTS" };

module.exports = async (app, opt) => {
  const client = axios.create({ timeout: 1000 });
  app.get(META.api, async () => ({ class: [], list: client ? [] : [] }));
  opt.sites.push(META);
};

module.exports.META = META;
"""


def test_loader_loads_local_js_plugin_with_node_runtime(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "js-plugin.js"
    plugin_path.write_text(JS_PLUGIN_SOURCE, encoding="utf-8")
    seen: dict[str, object] = {}

    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            seen["plugin_path"] = Path(plugin_path)
            seen["cache_dir"] = Path(cache_dir)
            seen["plugin_id"] = plugin_id

        def init(self, extend=""):
            seen["extend"] = extend

        def getName(self):
            return "JS短剧"

        def supports_search(self):
            return True

        def searchContent(self, key, quick, pg=1, category=""):
            return {"list": []}

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=51,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
        config_text="site=https://example.com",
    )

    loaded = loader.load(config)

    assert loaded.plugin_name == "JS短剧"
    assert loaded.search_enabled is True
    assert seen["plugin_path"] == plugin_path
    assert seen["cache_dir"] == tmp_path / "cache" / "spider-cache"
    assert seen["plugin_id"] == 51
    assert seen["extend"] == "site=https://example.com"


def test_loader_caches_remote_js_source_with_js_suffix(monkeypatch, tmp_path: Path) -> None:
    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            self.plugin_path = Path(plugin_path)

        def init(self, extend=""):
            return None

        def getName(self):
            return "JS短剧"

        def supports_search(self):
            return True

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        return httpx.Response(200, text=JS_PLUGIN_SOURCE, request=httpx.Request("GET", url))

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get)
    config = SpiderPluginConfig(
        id=52,
        source_type="remote",
        source_value="https://example.com/plugin.js",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "JS短剧"
    assert loaded.config.cached_file_path.endswith("plugin_52.js")
    assert Path(loaded.config.cached_file_path).read_text(encoding="utf-8") == JS_PLUGIN_SOURCE


def test_loader_detects_suffixless_remote_js_source(monkeypatch, tmp_path: Path) -> None:
    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            self.plugin_path = Path(plugin_path)

        def init(self, extend=""):
            return None

        def getName(self):
            return "JS短剧"

        def supports_search(self):
            return True

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)
    loader = SpiderPluginLoader(
        cache_dir=tmp_path / "cache",
        get=lambda url, **kwargs: httpx.Response(200, text=JS_PLUGIN_SOURCE, request=httpx.Request("GET", url)),
    )
    config = SpiderPluginConfig(
        id=53,
        source_type="remote",
        source_value="https://example.com/plugin",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.config.cached_file_path.endswith("plugin_53.js")


def test_loader_resolves_github_blob_txt_url_before_detecting_remote_source(
    monkeypatch, tmp_path: Path
) -> None:
    requested_urls: list[str] = []

    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            self.plugin_path = Path(plugin_path)

        def init(self, extend=""):
            return None

        def getName(self):
            return "JS短剧"

        def supports_search(self):
            return True

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)

    def fake_get(url: str, **kwargs) -> httpx.Response:
        requested_urls.append(url)
        return httpx.Response(
            200, text=JS_PLUGIN_SOURCE, request=httpx.Request("GET", url)
        )

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get)
    config = SpiderPluginConfig(
        id=56,
        source_type="remote",
        source_value="https://github.com/example/spiders/blob/main/py/%E7%9F%AD%E5%89%A7.txt",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "JS短剧"
    assert requested_urls == [
        "https://raw.githubusercontent.com/example/spiders/main/py/%E7%9F%AD%E5%89%A7.txt"
    ]
    assert loaded.config.cached_file_path.endswith("plugin_56.js")


def test_loader_detects_suffixless_remote_t4_commonjs_source(
    monkeypatch, tmp_path: Path
) -> None:
    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            self.plugin_path = Path(plugin_path)

        def init(self, extend=""):
            return None

        def getName(self):
            return "酷我听书"

        def supports_search(self):
            return True

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)

    def fake_get(url: str, **kwargs) -> httpx.Response:
        return httpx.Response(
            200, text=T4_PLUGIN_SOURCE, request=httpx.Request("GET", url)
        )

    loader = SpiderPluginLoader(
        cache_dir=tmp_path / "cache",
        get=fake_get,
    )
    config = SpiderPluginConfig(
        id=55,
        source_type="remote",
        source_value="https://example.com/t4",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "酷我听书"
    assert loaded.config.cached_file_path.endswith("plugin_55.js")


def test_loader_disables_search_for_js_plugin_without_search_method(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "no-search.js"
    plugin_path.write_text("export default { home() { return { class: [], list: [] } } }", encoding="utf-8")

    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            return None

        def init(self, extend=""):
            return None

        def getName(self):
            return "无搜索JS"

        def supports_search(self):
            return False

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=54,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config)

    assert loaded.search_enabled is False


def test_loader_loads_remote_secspider_plugin_and_persists_cache(tmp_path: Path) -> None:
    package_text, keyring = build_secspider_package(
        """
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "远程加密"
""",
        name="远程加密",
    )

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        return httpx.Response(200, text=package_text)

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get, keyring=keyring)
    config = SpiderPluginConfig(
        id=42,
        source_type="remote",
        source_value="https://example.com/encrypted.py",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "远程加密"
    assert Path(loaded.config.cached_file_path).read_text(encoding="utf-8").startswith("// ignore")


def test_loader_detects_remote_txt_secspider_format_below_metadata_headers(tmp_path: Path) -> None:
    package_text, keyring = build_secspider_package(
        """
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "远程TXT加密"
""",
        name="远程TXT加密",
    )

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        return httpx.Response(200, text=package_text)

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get, keyring=keyring)
    config = SpiderPluginConfig(
        id=57,
        source_type="remote",
        source_value="https://example.com/encrypted.txt",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "远程TXT加密"
    assert loaded.config.cached_file_path.endswith("plugin_57.py")


def test_loader_reports_secspider_signature_failure(tmp_path: Path) -> None:
    package_text, keyring = build_secspider_package("class Spider:\n    pass\n")
    plugin_path = tmp_path / "broken_encrypted.py"
    plugin_path.write_text(package_text.replace("payload.base64:", "payload.base64:Z", 1), encoding="utf-8")
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", keyring=keyring)
    config = SpiderPluginConfig(
        id=43,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
    )

    with pytest.raises(ValueError, match="插件签名校验失败"):
        loader.load(config)


def test_loader_reports_missing_spider_class_after_secspider_decrypt(tmp_path: Path) -> None:
    package_text, keyring = build_secspider_package("class NotSpider:\n    pass\n")
    plugin_path = tmp_path / "missing_spider.py"
    plugin_path.write_text(package_text, encoding="utf-8")
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", keyring=keyring)
    config = SpiderPluginConfig(
        id=44,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
    )

    with pytest.raises(ValueError, match="缺少 Spider 类"):
        loader.load(config)
