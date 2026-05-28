from __future__ import annotations

import json
import queue
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from atv_player.plugins.node_spider import NodeSpider


class FakeStdin:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, value: str) -> int:
        self.lines.append(value)
        return len(value)

    def flush(self) -> None:
        return None


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = queue.Queue()
        for line in lines:
            self._lines.put(line)

    def readline(self) -> str:
        try:
            return self._lines.get_nowait()
        except queue.Empty:
            return ""


class FakeStderr:
    def readline(self) -> str:
        return ""


class FakeProcess:
    def __init__(self, lines: list[str]) -> None:
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(lines)
        self.stderr = FakeStderr()
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):
        return 0


def test_node_spider_reports_missing_node(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "atv_player.plugins.node_spider.shutil.which", lambda name: None
    )

    with pytest.raises(ValueError, match="未找到 Node.js 运行环境"):
        NodeSpider(
            plugin_path=tmp_path / "plugin.js",
            cache_dir=tmp_path / "cache",
            plugin_id=1,
        )


def test_node_spider_calls_bridge_methods(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "plugin.js"
    plugin_path.write_text("export default {}", encoding="utf-8")
    fake_process = FakeProcess(
        [
            json.dumps({"id": 1, "ok": True, "result": "JS插件"}) + "\n",
            json.dumps({"id": 2, "ok": True, "result": {"class": [], "list": []}})
            + "\n",
            json.dumps({"id": 3, "ok": True, "result": True}) + "\n",
        ]
    )
    popen_calls: list[list[str]] = []

    def fake_popen(command, **kwargs):
        popen_calls.append(command)
        return fake_process

    monkeypatch.setattr(
        "atv_player.plugins.node_spider.shutil.which", lambda name: "/usr/bin/node"
    )
    monkeypatch.setattr("atv_player.plugins.node_spider.subprocess.Popen", fake_popen)

    spider = NodeSpider(
        plugin_path=plugin_path,
        cache_dir=tmp_path / "cache",
        plugin_id=7,
        timeout_seconds=1,
    )

    assert spider.getName() == "JS插件"
    assert spider.homeContent(False) == {"class": [], "list": []}
    assert spider.supports_search() is True
    assert popen_calls[0][0] == "/usr/bin/node"
    assert "--plugin" in popen_calls[0]
    assert str(plugin_path) in popen_calls[0]
    assert json.loads(fake_process.stdin.lines[0]) == {
        "id": 1,
        "method": "getName",
        "args": [],
    }
    assert json.loads(fake_process.stdin.lines[1]) == {
        "id": 2,
        "method": "home",
        "args": [False],
    }
    assert json.loads(fake_process.stdin.lines[2]) == {
        "id": 3,
        "method": "hasMethod",
        "args": ["search"],
    }


def test_node_spider_raises_bridge_error(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "plugin.js"
    plugin_path.write_text("export default {}", encoding="utf-8")
    fake_process = FakeProcess(
        [json.dumps({"id": 1, "ok": False, "error": "boom"}) + "\n"]
    )

    monkeypatch.setattr(
        "atv_player.plugins.node_spider.shutil.which", lambda name: "/usr/bin/node"
    )
    monkeypatch.setattr(
        "atv_player.plugins.node_spider.subprocess.Popen",
        lambda command, **kwargs: fake_process,
    )

    spider = NodeSpider(
        plugin_path=plugin_path,
        cache_dir=tmp_path / "cache",
        plugin_id=7,
        timeout_seconds=1,
    )

    with pytest.raises(RuntimeError, match="boom"):
        spider.homeContent(False)


pytestmark_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is not installed"
)


@pytestmark_node
def test_node_bridge_loads_default_export_fixture(tmp_path: Path) -> None:
    plugin_path = tmp_path / "default-plugin.mjs"
    plugin_path.write_text(
        """
export default {
  init(ext) { this.ext = ext },
  getName() { return `默认:${this.ext}` },
  home(filter) { return { class: [{ type_id: "hot", type_name: "热门" }], list: [] } },
  category(tid, pg, filter, extend) {
    return { list: [{ vod_id: `${tid}-${pg}`, vod_name: "分类" }], total: 1 }
  },
  detail(id) {
    return {
      list: [{
        vod_id: id,
        vod_name: "详情",
        vod_play_from: "默认线",
        vod_play_url: "第1集$/play/1"
      }]
    }
  },
  search(key, quick, pg) {
    return { list: [{ vod_id: key, vod_name: key }], total: 1 }
  },
  play(flag, id, vipFlags) {
    return {
      parse: 0,
      url: `https://media.example${id}.m3u8`,
      header: { Referer: "https://site.example" }
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    spider = NodeSpider(
        plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=1
    )

    spider.init("ext")

    assert spider.getName() == "默认:ext"
    assert spider.homeContent(False)["class"][0]["type_name"] == "热门"
    assert spider.categoryContent("hot", "2", False, {})["list"][0]["vod_id"] == "hot-2"
    assert spider.detailContent(["abc"])["list"][0]["vod_name"] == "详情"
    assert spider.searchContent("关键字", False, "1")["list"][0]["vod_name"] == "关键字"
    assert (
        spider.playerContent("默认线", "/play/1", [])["url"]
        == "https://media.example/play/1.m3u8"
    )
    spider.destroy()


@pytestmark_node
def test_node_bridge_loads_js_eval_return_fixture_and_local_cache(
    tmp_path: Path,
) -> None:
    plugin_path = tmp_path / "eval-plugin.mjs"
    plugin_path.write_text(
        """
export function __jsEvalReturn() {
  return {
    init(ext) { local.set("rule", "ext", ext) },
    getName() { return `缓存:${local.get("rule", "ext")}` },
    home() {
      return JSON.stringify({
        class: [],
        list: [{ vod_id: "1", vod_name: "首页" }]
      })
    },
    category() { return { list: [], total: 0 } },
    detail(id) {
      return {
        list: [{
          vod_id: id,
          vod_name: "详情",
          vod_play_from: "默认",
          vod_play_url: "正片$https://media.example/a.m3u8"
        }]
      }
    },
    play(flag, id) { return { parse: 0, url: id } }
  }
}
""".strip(),
        encoding="utf-8",
    )
    spider = NodeSpider(
        plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=2
    )

    spider.init("abc")

    assert spider.getName() == "缓存:abc"
    assert spider.homeContent(False)["list"][0]["vod_name"] == "首页"
    spider.destroy()


@pytestmark_node
def test_node_bridge_loads_t4_commonjs_route_plugin(tmp_path: Path) -> None:
    plugin_path = tmp_path / "t4-plugin.cjs"
    plugin_path.write_text(
        """
const axios = require("axios");
const http = require("http");
const https = require("https");

const client = axios.create({
  timeout: 1000,
  httpAgent: new http.Agent({ keepAlive: true }),
  httpsAgent: new https.Agent({ rejectUnauthorized: false })
});

const META = {
  key: "KuWoTS",
  name: "酷我听书",
  type: 4,
  api: "/video/KuWoTS",
  searchable: 2,
  quickSearch: 0,
  filterable: 1
};

module.exports = async (app, opt) => {
  app.get(META.api, async (req) => {
    const { ids, play, wd, t, pg, ext } = req.query;
    if (play) {
      return { parse: 0, url: play, header: { "User-Agent": "demo" } };
    }
    if (ids) {
      return {
        list: [{
          vod_id: ids,
          vod_name: "详情",
          vod_play_from: "kuwo",
          vod_play_url: "第1集$http://play.example/a.mp3"
        }]
      };
    }
    if (wd) {
      return {
        list: [{ vod_id: `search-${wd}-${pg}`, vod_name: wd }],
        page: Number(pg),
        total: 1
      };
    }
    if (t) {
      const filters = JSON.parse(Buffer.from(ext, "base64").toString());
      return {
        list: [{
          vod_id: `${t}-${pg}-${filters.class}-${filters.vip}`,
          vod_name: "分类"
        }],
        page: Number(pg),
        total: 1
      };
    }
    return {
      class: [{ type_id: "2", type_name: "有声小说" }],
      filters: {
        "2": [{
          key: "class",
          name: "类型",
          value: [{ n: "都市传说", v: "42" }]
        }]
      },
      list: [{
        vod_id: "album-1",
        vod_name: "首页",
        vod_remarks: client ? "ok" : "bad"
      }]
    };
  });
  opt.sites.push(META);
};

module.exports.META = META;
""".strip(),
        encoding="utf-8",
    )
    spider = NodeSpider(
        plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=3
    )

    assert spider.getName() == "酷我听书"
    assert spider.homeContent(False)["class"][0]["type_name"] == "有声小说"
    category = spider.categoryContent("2", "3", False, {"class": "44", "vip": "0"})
    assert category["list"][0]["vod_id"] == "2-3-44-0"
    assert spider.detailContent(["album-1"])["list"][0]["vod_play_from"] == "kuwo"
    search = spider.searchContent("abc", False, "2")
    assert search["list"][0]["vod_id"] == "search-abc-2"
    assert (
        spider.playerContent("kuwo", "http://play.example/a.mp3", [])["url"]
        == "http://play.example/a.mp3"
    )
    assert spider.supports_search() is True
    spider.destroy()


@pytestmark_node
def test_node_bridge_supports_fastify_style_t4_plugin_with_axios_post(
    tmp_path: Path,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "sid=abc")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "body": body}).encode("utf-8"))

        def log_message(self, format, *args) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api_url = f"http://127.0.0.1:{server.server_port}/api"

    plugin_path = tmp_path / "nongmin.cjs"
    plugin_path.write_text(
        """
const axios = require("axios");
const crypto = require("crypto");
const https = require("https");

module.exports = async (server, opt) => {
  const SITE_NAME = "农民影视";
  const http = axios.create({
    timeout: 10000,
    responseType: "text",
    transformResponse: [(data) => data],
    httpsAgent: new https.Agent({ rejectUnauthorized: false }),
    validateStatus: (s) => s >= 200 && s < 400
  });

  server.get("/video/nongmin", async (req, reply) => {
    const q = req.query || {};
    if (q.play) {
      return reply.send({
        parse: 0,
        url: `${q.flag || q.from || ""}|${q.play}`,
        header: { post: http.post ? "yes" : "no" }
      });
    }
    if (q.wd) {
      const body = new URLSearchParams({ wd: q.wd }).toString();
      const resp = await http.post("__API_URL__", body, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" }
      });
      return reply.send({
        list: [{
          vod_id: crypto.createHash("md5").update(resp.data).digest("hex"),
          vod_name: resp.headers["set-cookie"][0]
        }]
      });
    }
    return reply.send({
      class: [{ type_id: "dianying", type_name: "电影" }],
      list: []
    });
  });

  opt.sites.push({ name: SITE_NAME, api: "/video/nongmin" });
};
""".strip().replace("__API_URL__", api_url),
        encoding="utf-8",
    )

    try:
        spider = NodeSpider(
            plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=4
        )

        assert spider.getName() == "农民影视"
        assert spider.homeContent(False)["class"][0]["type_name"] == "电影"
        search = spider.searchContent("麦田", False, "1")
        assert search["list"][0]["vod_name"] == "sid=abc"
        assert spider.playerContent("线路A", "/play/1", [])["url"] == "线路A|/play/1"
        spider.destroy()
    finally:
        server.shutdown()
        server.server_close()


@pytestmark_node
def test_node_bridge_supports_t4_plugin_with_callable_axios_instance(
    tmp_path: Path,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"posted:{body}".encode())

        def log_message(self, format, *args) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api_url = f"http://127.0.0.1:{server.server_port}/search"

    plugin_path = tmp_path / "nmdvd-callable.cjs"
    plugin_path.write_text(
        """
const axios = require("axios");
const crypto = require("crypto");
const https = require("https");
const http = require("http");

const httpClient = axios.create({
  timeout: 15000,
  httpAgent: new http.Agent({ keepAlive: true }),
  httpsAgent: new https.Agent({ keepAlive: true, rejectUnauthorized: false })
});

const request = async (url, options = {}) => {
  const response = await httpClient({
    url,
    method: options.method || "GET",
    headers: options.headers || {},
    data: options.data || undefined,
    responseType: options.responseType || "text",
    maxRedirects: 5
  });
  return response;
};

const handleT4Request = async (req) => {
  const { t, pg, wd, ids, play, extend } = req.query;
  if (wd) {
    const response = await request("__API_URL__", {
      method: "POST",
      data: `wd=${encodeURIComponent(wd)}&submit=`,
      headers: { "Content-Type": "application/x-www-form-urlencoded" }
    });
    return {
      list: [{
        vod_id: crypto.createHash("md5").update(response.data).digest("hex"),
        vod_name: response.data
      }]
    };
  }
  if (play) return { parse: 0, url: play };
  if (ids) return { list: [{ vod_id: ids, vod_name: "详情" }] };
  if (t) {
    const extendParams = extend ? JSON.parse(extend) : {};
    return {
      list: [{ vod_id: `${t}-${pg}-${extendParams.area || "none"}` }]
    };
  }
  return {
    class: [{ type_id: "dianying", type_name: "电影" }],
    list: []
  };
};

const meta = {
  key: "农民影视",
  name: "农民影视",
  api: "/video/nmdvd"
};

module.exports = async (app, opt) => {
  app.get(meta.api, async (req, reply) => {
    const result = await handleT4Request(req);
    return result;
  });
  opt.sites.push(meta);
};
""".strip().replace("__API_URL__", api_url),
        encoding="utf-8",
    )

    try:
        spider = NodeSpider(
            plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=5
        )

        assert spider.getName() == "农民影视"
        assert spider.homeContent(False)["class"][0]["type_name"] == "电影"
        search = spider.searchContent("麦田", False, "1")
        assert search["list"][0]["vod_name"] == "posted:wd=%E9%BA%A6%E7%94%B0&submit="
        category = spider.categoryContent("dianying", "2", False, {"area": "内地"})
        assert category["list"][0]["vod_id"] == "dianying-2-内地"
        assert spider.detailContent(["/detail/1"])["list"][0]["vod_name"] == "详情"
        assert spider.playerContent("默认", "/play/1", [])["url"] == "/play/1"
        spider.destroy()
    finally:
        server.shutdown()
        server.server_close()


@pytestmark_node
def test_node_bridge_supports_t4_plugin_with_uuid_and_json_post(
    tmp_path: Path,
) -> None:
    seen: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/apptov5/v1/config/get"):
                payload = {
                    "data": {
                        "get_home_cate": [
                            {"cate": "movie", "title": "电影", "extend": {}}
                        ],
                        "get_parsing": {
                            "lists": [
                                {
                                    "key": "lineA",
                                    "config": [{"type": "json", "label": "json1"}],
                                }
                            ]
                        },
                    }
                }
            elif self.path.startswith("/apptov5/v1/home/data"):
                payload = {
                    "data": {
                        "sections": [
                            {
                                "items": [
                                    {
                                        "vod_id": "1",
                                        "vod_name": "首页片",
                                        "vod_pic": "mac://img.test/a.jpg",
                                    }
                                ]
                            }
                        ]
                    }
                }
            elif self.path.startswith("/apptov5/v1/vod/lists"):
                payload = {
                    "data": {
                        "data": [
                            {
                                "vod_id": "cat-1",
                                "vod_name": "分类片",
                                "vod_pic": "mac://img.test/b.jpg",
                            }
                        ],
                        "total": 21,
                    }
                }
            elif self.path.startswith("/apptov5/v1/search/lists"):
                payload = {
                    "data": {
                        "data": [{"vod_id": "search-1", "vod_name": "搜索片"}],
                        "total": 1,
                    }
                }
            elif self.path.startswith("/apptov5/v1/vod/getVod"):
                payload = {
                    "data": {
                        "vod_id": "1",
                        "vod_name": "详情片",
                        "vod_play_list": [
                            {
                                "player_info": {"from": "lineA", "show": "线路A"},
                                "urls": [{"name": "第1集", "url": "raw-url"}],
                            }
                        ],
                    }
                }
            else:
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            seen["content_type"] = self.headers.get("Content-Type", "")
            seen["body"] = body
            payload = {
                "data": {
                    "url": "http://media.example/a.m3u8",
                    "UA": "App-UA",
                }
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, format, *args) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"http://127.0.0.1:{server.server_port}"

    plugin_path = tmp_path / "ppx.cjs"
    plugin_path.write_text(
        """
const axios = require("axios");
const http = require("http");
const https = require("https");
const { v4: uuidv4 } = require("uuid");

const _http = axios.create({
  timeout: 15000,
  httpsAgent: new https.Agent({ keepAlive: true, rejectUnauthorized: false }),
  httpAgent: new http.Agent({ keepAlive: true })
});

const ppxConfig = {
  host: "__HOST__",
  local_uuid: uuidv4(),
  config: null,
  parsing_config: {},
  headers: { "User-Agent": "Dart/2.19", token: "token" }
};

const initConfig = async () => {
  ppxConfig.headers["appto-local-uuid"] = ppxConfig.local_uuid;
  const response = await _http.get(
    `${ppxConfig.host}/apptov5/v1/config/get?p=android`,
    { headers: ppxConfig.headers }
  );
  const data = response.data.data || {};
  ppxConfig.config = data;
  const parsingConfig = {};
  for (const item of data.get_parsing.lists || []) {
    parsingConfig[item.key] = item.config
      .filter((conf) => conf.type === "json")
      .map((conf) => conf.label);
  }
  ppxConfig.parsing_config = parsingConfig;
};

const getClasses = async () => {
  if (!ppxConfig.config) await initConfig();
  return (ppxConfig.config.get_home_cate || []).map((item) => ({
    type_id: item.cate,
    type_name: item.title
  }));
};

const getHomeRecommend = async () => {
  const response = await _http.get(`${ppxConfig.host}/apptov5/v1/home/data`);
  return response.data.data.sections[0].items.map((item) => ({
    ...item,
    vod_pic: item.vod_pic.replace("mac://", "http://")
  }));
};

const getCategoryList = async (tid, pg, extend = {}) => {
  const params = `type_id=${tid}&area=${extend.area || ""}&page=${pg}`;
  const response = await _http.get(`${ppxConfig.host}/apptov5/v1/vod/lists?${params}`);
  return {
    list: response.data.data.data,
    page: parseInt(pg),
    pagecount: Math.ceil(response.data.data.total / 21),
    total: response.data.data.total
  };
};

const searchVod = async (keyword, page = 1) => {
  const params = `wd=${encodeURIComponent(keyword)}&page=${page}`;
  const url = `${ppxConfig.host}/apptov5/v1/search/lists?${params}`;
  const response = await _http.get(url);
  return {
    list: response.data.data.data,
    page: parseInt(page),
    pagecount: 1,
    total: 1
  };
};

const getDetail = async (id) => {
  const response = await _http.get(`${ppxConfig.host}/apptov5/v1/vod/getVod?id=${id}`);
  const data = response.data.data;
  let vod_play_from = "";
  let vod_play_url = "";
  for (const item of data.vod_play_list || []) {
    const urls = item.urls
      .map((play) => `${play.name}$${item.player_info.from}@${play.url}`)
      .join("#");
    vod_play_from += `${item.player_info.show}$$$`;
    vod_play_url += `${urls}$$$`;
  }
  return {
    vod_id: data.vod_id,
    vod_name: data.vod_name,
    vod_play_from: vod_play_from.replace(/\\$\\$\\$$/, ""),
    vod_play_url: vod_play_url.replace(/\\$\\$\\$$/, "")
  };
};

const getPlayUrl = async (playId) => {
  const [playfrom, rawurl] = playId.split("@");
  const response = await _http.post(
    `${ppxConfig.host}/apptov5/v1/parsing/proxy`,
    { play_url: rawurl, label: ppxConfig.parsing_config[playfrom][0], key: playfrom },
    { headers: ppxConfig.headers }
  );
  return {
    parse: 0,
    url: response.data.data.url,
    header: { "User-Agent": response.data.data.UA }
  };
};

const handleT4Request = async (req) => {
  const { t, pg, wd, ids, play, extend } = req.query;
  if (wd) return await searchVod(wd, pg);
  if (play) return await getPlayUrl(play);
  if (ids) return { list: [await getDetail(ids)] };
  if (t) return await getCategoryList(t, pg, extend ? JSON.parse(extend) : {});
  return { class: await getClasses(), list: await getHomeRecommend() };
};

const meta = { key: "皮皮虾", name: "皮皮虾T4", api: "/video/皮皮虾" };

module.exports = async (app, opt) => {
  await initConfig();
  app.get(meta.api, async (req) => await handleT4Request(req));
  opt.sites.push(meta);
};
""".strip().replace("__HOST__", host),
        encoding="utf-8",
    )

    try:
        spider = NodeSpider(
            plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=6
        )

        assert spider.getName() == "皮皮虾T4"
        assert (
            spider.homeContent(False)["list"][0]["vod_pic"] == "http://img.test/a.jpg"
        )
        category = spider.categoryContent("movie", "2", False, {"area": "内地"})
        assert category["list"][0]["vod_name"] == "分类片"
        assert (
            spider.searchContent("abc", False, "1")["list"][0]["vod_name"] == "搜索片"
        )
        detail = spider.detailContent(["1"])["list"][0]
        assert detail["vod_play_url"] == "第1集$lineA@raw-url"
        play = spider.playerContent("线路A", "lineA@raw-url", [])
        assert play["url"] == "http://media.example/a.m3u8"
        assert play["header"]["User-Agent"] == "App-UA"
        assert seen["content_type"].startswith("application/json")
        assert json.loads(seen["body"]) == {
            "play_url": "raw-url",
            "label": "json1",
            "key": "lineA",
        }
        spider.destroy()
    finally:
        server.shutdown()
        server.server_close()
