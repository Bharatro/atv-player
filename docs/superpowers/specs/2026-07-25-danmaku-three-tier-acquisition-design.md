# 弹幕三级获取链设计

## 背景

`atv-player` 原生支持腾讯、优酷、B站、爱奇艺、芒果、搜狐、咪咕、人人八个直连弹幕 provider。本轮从一个真实故障（腾讯《百花杀》第13集搜不到、内容无关）出发，系统排查后发现三层独立缺陷，并参考本地 `/home/harold/workspace/danmu_api` 的 source 经验，把弹幕获取重构成一条三级回退链：**内置直连 → 豆瓣发现 → 第三方兜底**。

全程保持 `atv-player` 原生直连：运行时不依赖用户部署 `danmu_api`，也不调用其聚合接口，仅移植其匹配与发现经验。

## 已修复的底层缺陷（回归基线）

这些是本轮排查出的真实 bug，后续改动必须保留其回归测试：

1. **腾讯 vid 取错致弹幕内容无关**（`61d1148d`）：`_extract_video_id` 原先优先抓页面 HTML 里的 `videoId/vid`，而剧集页 HTML 嵌有推广 vid（如 `s00242sxrne`），导致每集都解析到同一个推广 vid、返回同一段无关弹幕。修复：URL vid 优先（query → path），HTML 仅兜底。
2. **多同名剧 cover-id 消歧**（`538ecfb7`）：同名剧（如正剧与同名短剧）在候选里混杂时，按 `reg_src` 的 cover_id 稳健选中用户实际在播的剧，不再依赖 MbSearch 返回顺序的运气。
3. **多同名剧展开早退**：MbSearch 同时返回正剧与同名短剧，短剧快照里的同集号会误触发"已找到"早退，导致用户的正剧从未被展开。修复：候选跨越多个 cover_id 时不早退。
4. **剧情式集标题匹配**：腾讯分集名是 `第十三集 <剧情字幕>`（不含剧名），原相似度/标题门会误删。修复：以集标记开头的候选放行，但仍拒绝异名同集号剧。
5. **非法 XML 控制字符**：单条弹幕含 `\x08` 等 XML 1.0 非法控制字符会导致整份 XML 解析失败（"弹幕为空"）。修复：`build_xml` 生成时剥离、`_parse_danmaku_xml_records` 解析时剥离（自愈旧缓存）。

## 目标

- 内置直连搜不到时，用豆瓣发现跨平台找回播放链接并复用现有 provider 展开分集。
- 豆瓣也搜不到时，用第三方弹幕服务兜底覆盖冷门剧。
- 保持现有 provider 协议、单源加载模型、有界并发、按来源禁用等能力不变。
- 每一级都经真实网络端到端验证。

## 非目标

- 不内置或部署 `danmu_api` 服务。
- 不实现跨来源弹幕合并、时间轴对齐或去重。
- 不移植巴哈姆特、埋堆堆、爱壹帆等 provider。
- 不实现跨季连续集号顺延（`findCrossSeasonEpisodeMap`）——目前无具体失败用例，暂不做。

## 总体架构

三级回退在 `DanmakuService.search_danmu` 中串联，每级为空才进入下一级：

```
search_danmu(name, reg_src)
  ├─ 1. 内置直连: provider.search() → 候选              (原有路径)
  ├─ 2. 若空: _discover_via_douban()                    (本轮新增)
  │        豆瓣 search → subject → fetch_vendors →
  │        vendor_to_page_url → provider.expand_page_url() → 候选
  └─ 3. 若仍空且 reg_src 是 http 播放页: other 兜底候选   (本轮新增)
           OtherDanmakuProvider.resolve(reg_src)
```

`resolve_danmu` 相应支持路由到 `other`（不在 `provider_order`，但被选中时可 resolve）。

## 一级：内置直连（原有）

八个 provider 各自 `search` → 展开分集 → `resolve`。缺陷 1-5 均在此层修复。

## 二级：豆瓣发现（`c1280aa6` + `30715a38`）

### 发现模块 `discovery/douban.py`

豆瓣是**元源**：自己不分集、不产弹幕，只提供"这部剧在哪些平台能看"。

- `search_subjects(keyword)`：调 rexxar `search` 接口取 subject（title/year/type/doubanId）；主接口失败或空时兜底到 public-api（`api.douban.com/v2/movie/search`，硬编码 apikey）。
- `fetch_vendors(douban_id)`：调 rexxar `detail` 接口，从 `vendors`（"在哪儿看"）解析各平台 mediaId：
  - qq → cid、iqiyi → tvid、youku → showid、bilibili → `ss{seasonId}`、migu → content-info URL（uri 是 URL-encoded JSON，需 decode 后正则取 contentID）
  - 未知 vendor（netflix/pptv 等）跳过。
- `vendor_to_page_url(vendor)`：mediaId → 各平台可被对应 provider 接受的 URL。
  - tencent 必须构造 `/x/cover/{cid}/`（尾斜杠，否则 `_extract_cover_id` 正则不匹配）。

### provider 的 `expand_page_url(page_url, query_name)`

豆瓣给的是剧总览级 mediaId，需各 provider 从中展开出全部分集。实测发现**四个平台展开路径差异很大**：

| provider | 展开方式 | 说明 |
|---|---|---|
| bilibili | 薄封装 | `_candidate_from_page_url` → season API（`pgc/view/web/season`），无需 wbi/SPI |
| iqiyi | 移植专用 API | 数字 tvid 页无 `album-avlist-data`；需 `baseinfo/{tvid}` → albumId → `avlistinfo?aid=` 分页 |
| youku | 移植专用 API | showid 页是 JS 动态渲染，HTML 抓不到；需 `shows/videos.json?show_id=` 分页 |
| migu | 复用 `_detail`/`_episodes` | content-info → `body.data.datas`，每集带 pID |

**关键教训**：iqiyi/youku/migu 现有的 HTML 抓取路径吃不下豆瓣的 mediaId，必须移植 danmu_api 的专用 API（非薄封装）。这与最初"四个都薄封装"的预期不同，是靠真实网络探针才暴露出来的——先探针验证再实现，避免了白做。

## 三级：第三方兜底（`67883eea`）

### `providers/other.py`

- `OtherDanmakuProvider.resolve(page_url)`：调第三方弹幕服务（默认 `dmku.hls.one`，`?ac=dm&url=`），`danmuku` payload → records（right/top/bottom → pos 1/5/4，空内容跳过）。
- `supports()` 恒为 True，但**不进 `provider_order`**——不参与正常搜索排序，只在前两级全空时作为最后候选，resolve URL 用 `reg_src`。

与 atv-player 已有的 `DirectParseDanmakuController`（直链播放路径专用，同样用 `dmku.hls.one`）逻辑一致，但接入的是主路径 `DanmakuService`。

## 装配

`create_default_danmaku_service` 默认构造并注入 `DoubanDiscovery` 和 `OtherDanmakuProvider`，`app.py` 调用该 factory，无需额外改动即运行时生效。

## 运行时风险

1. **豆瓣 rexxar 限流**：主接口高频使用会触发 403 `need_login`。依赖 public-api 兜底 + 硬编码 apikey（`0ac44ae016490db2204ce0a042db2916`，可能随时失效）。生产环境可考虑配 `DOUBAN_COOKIE` 或降低请求频率。
2. **平台 content id 失效**：iqiyi/migu 的部分 content id 会返回 410 / 参数错误（数据个例，非代码问题）。
3. **第三方服务依赖**：`dmku.hls.one` 弹幕量偏少（实测冷门剧约 88-122 条，含 1 条服务提示弹幕），且完全依赖其可用性与数据质量。

## 真实网络端到端验证

- 豆瓣发现：《百花杀》内置置空后经豆瓣找回完整 29 集，ep13 URL 正确。
- 四 provider expand：bilibili 鬼灭之刃 26 集（带 cid）、iqiyi 赘婿 30 集、youku 点燃我温暖你 37 集、migu 三体 30 集（URL 各唯一）。
- 三级兜底：内置+豆瓣双空 → other → 真实取到 122 条弹幕（dmku.hls.one）。

## 提交记录

| 提交 | 内容 |
|---|---|
| `61d1148d` | 腾讯 vid 取错（弹幕内容无关） |
| `538ecfb7` | 多同名剧 cover-id 消歧 |
| `c1280aa6` | 豆瓣发现回退 |
| `30715a38` | 四 provider 发现层路由 |
| `67883eea` | 第三方兜底源（other） |
