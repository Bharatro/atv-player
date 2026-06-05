# Heat Recommendation Client Design

## Goal

将用户的搜索、播放、收藏、追更等匿名操作上报到固定后端，由后端聚合成真实热度推荐，并在 ATV Player 中展示给其他用户。

## Decisions

- 使用自建后端，不接入 `https://www.252035.xyz/xs/tvbox/nostr.html` 的 Nostr relay 方案。
- 第一版只实现客户端接入协议，不在本仓库实现后端。
- 后端地址固定为 `https://v.har01d.cn/api/v1/heat`，不提供用户配置入口。
- 第一版使用 HTTP API，不使用 WebSocket 或 gRPC。
- 用户无感知：不弹配置、不显示同步状态、不因热度 API 失败打断播放或搜索。
- 使用匿名安装 ID 做上报身份，不上传账号、token、播放 URL、网盘链接、cookie、插件鉴权信息。

## Scope

- 新增客户端热度 service/controller，负责匿名事件上报和热度数据读取。
- 在全局搜索框后的现有热榜弹窗中加入“大家在看”推荐分区。
- 点击推荐媒体触发现有全局搜索；如果后续能稳定映射到追更候选，再扩展为打开追更详情。
- 播放窗口详情区异步显示热度摘要，例如 `X 人正在播放`。
- 收藏、追更、搜索、播放开始、有效观看等行为触发后台上报。

## Out Of Scope

- 不实现 Go 后端。
- 不做账号级个性化推荐。
- 不提供用户可配置后端地址。
- 不上传播放源 URL 或任何鉴权凭据。
- 不做实时 WebSocket presence。`正在播放` 第一版由后端基于近窗口事件统计，客户端按摘要接口轮询或一次性读取。
- 不持久化本地待发送队列。失败事件静默丢弃。

## Architecture

新增 `HeatService` 作为底层 HTTP client，固定 base URL，提供：

- `record_event(event)`
- `load_recommendations(limit)`
- `load_media_heat(media_key)`

新增 `HeatController` 或在主窗口中注入一个薄 controller，负责把 UI/播放上下文转换为脱敏后的 heat payload。它不进入播放解析链，也不改变搜索、收藏、追更、播放历史的现有存储逻辑。

所有网络请求在后台线程执行，短超时，失败只写日志。UI 永远以“没有热度数据”作为降级状态。

## Backend API Contract

后端服务实现以下固定 HTTP JSON API。客户端会以 `https://v.har01d.cn/api/v1/heat` 为 base URL。

Full paths:

- `POST https://v.har01d.cn/api/v1/heat/events`
- `GET https://v.har01d.cn/api/v1/heat/recommendations?limit=24`
- `GET https://v.har01d.cn/api/v1/heat/media/{media_key}`

### Common Requirements

- Request `Content-Type`: `application/json; charset=utf-8` for POST.
- Response `Content-Type`: `application/json; charset=utf-8`.
- Client timeout target: 2-4 seconds.
- Server should accept unknown JSON fields for forward compatibility.
- Server should return stable JSON shapes even when data is empty.
- All timestamps use Unix epoch milliseconds unless explicitly named `*_seconds`.
- `media_key` must be URL-safe when used in path. Client will percent-encode it.

### Media Identity

The client sends the best available media identity:

```json
{
  "media_key": "tmdb:tv:1399",
  "title": "权力的游戏",
  "original_title": "Game of Thrones",
  "poster": "https://...",
  "year": "2011",
  "media_type": "tv",
  "external_ids": {
    "tmdb": "tv:1399",
    "douban": "3016187",
    "bangumi": ""
  }
}
```

`media_key` priority:

1. `tmdb:{movie|tv}:{id}`
2. `douban:{id}`
3. `bangumi:{id}`
4. `title:{normalized_title}` when no stable external ID exists

The Go backend should treat `media_key` as the primary key and may perform additional deduplication by `external_ids` and normalized title.

### POST `/events`

Records an anonymous client event.

Request:

```json
{
  "event_id": "01JZ0M0W37QK2R8H0R8K0BG5TS",
  "installation_id": "3d5f2d66-8d35-4e02-86f7-fd4dcdf28d2b",
  "event_type": "watch_progress",
  "occurred_at": 1780660000000,
  "client": {
    "app": "atv-player",
    "version": "0.69.1",
    "platform": "linux"
  },
  "media": {
    "media_key": "tmdb:tv:1399",
    "title": "权力的游戏",
    "original_title": "Game of Thrones",
    "poster": "https://image.tmdb.org/t/p/w342/...",
    "year": "2011",
    "media_type": "tv",
    "external_ids": {
      "tmdb": "tv:1399",
      "douban": "3016187"
    }
  },
  "context": {
    "source_kind": "plugin",
    "source_label": "插件",
    "query": "权力的游戏",
    "episode_index": 0,
    "position_seconds": 600,
    "duration_seconds": 2700,
    "effective_watch": true
  }
}
```

Required fields:

- `event_id`
- `installation_id`
- `event_type`
- `occurred_at`

Conditionally required fields:

- For `search`: `context.query` is required. `media` is optional.
- For `detail_open`, `play_start`, `watch_progress`, `favorite_add`, and `following_add`: `media.media_key` and `media.title` are required.
- For recommendation-click-to-search: send `event_type = "search"`, `context.query`, `context.source_kind = "heat_recommendation"`, and include `media` when the recommendation item has one.

Allowed `event_type` values:

- `search`
- `detail_open`
- `play_start`
- `watch_progress`
- `favorite_add`
- `following_add`

Context rules:

- `query` is allowed for `search` and recommendation-click-to-search flows.
- `position_seconds`, `duration_seconds`, `episode_index`, and `effective_watch` are allowed for playback events.
- Do not send playback URL, source URL, cookies, auth headers, API tokens, account names, or raw plugin config.

Minimal search event:

```json
{
  "event_id": "01JZ0M0W37QK2R8H0R8K0BG5TT",
  "installation_id": "3d5f2d66-8d35-4e02-86f7-fd4dcdf28d2b",
  "event_type": "search",
  "occurred_at": 1780660000000,
  "client": {
    "app": "atv-player",
    "version": "0.69.1",
    "platform": "linux"
  },
  "context": {
    "query": "权力的游戏",
    "source_kind": "global_search"
  }
}
```

Response success:

```json
{
  "ok": true,
  "accepted": true,
  "event_id": "01JZ0M0W37QK2R8H0R8K0BG5TS"
}
```

Recommended status codes:

- `202 Accepted` for accepted events.
- `200 OK` is also acceptable if the backend processes synchronously.
- `400 Bad Request` for invalid JSON or missing required fields.
- `413 Payload Too Large` for oversized payloads.
- `429 Too Many Requests` for rate limiting.
- `5xx` for server errors.

Client behavior:

- On `2xx`, treat event as delivered.
- On non-`2xx`, timeout, or network error, log and drop.
- No retry queue in first version.

Backend implementation notes:

- Deduplicate by `event_id`.
- Rate-limit by `installation_id` and IP.
- Consider ignoring `watch_progress` unless `effective_watch` is true.
- Count `play_start` for near-window currently-playing estimates.

### GET `/recommendations?limit=24`

Returns global heat recommendations for the popup.

Response:

```json
{
  "ok": true,
  "generated_at": 1780660000000,
  "window_seconds": 86400,
  "items": [
    {
      "media_key": "tmdb:tv:1399",
      "title": "权力的游戏",
      "original_title": "Game of Thrones",
      "poster": "https://image.tmdb.org/t/p/w342/...",
      "year": "2011",
      "media_type": "tv",
      "external_ids": {
        "tmdb": "tv:1399",
        "douban": "3016187"
      },
      "heat_score": 983.4,
      "rank": 1,
      "watching_now": 23,
      "recent_watchers": 128,
      "recent_searches": 42,
      "recent_favorites": 8,
      "reason": "128 人近期观看"
    }
  ]
}
```

Query:

- `limit`: optional integer, client first version sends `24`; server may cap to a safe maximum.

Required response fields per item:

- `media_key`
- `title`
- `heat_score`
- `rank`

Optional but recommended:

- `poster`
- `year`
- `media_type`
- `external_ids`
- `watching_now`
- `recent_watchers`
- `reason`

Empty response:

```json
{
  "ok": true,
  "generated_at": 1780660000000,
  "window_seconds": 86400,
  "items": []
}
```

Client behavior:

- Render a “大家在看” section when `items` is non-empty.
- Hide the section or show the popup's existing empty state when empty.
- Clicking an item triggers existing global search with `title`.

### GET `/media/{media_key}`

Returns heat summary for one media item.

Response:

```json
{
  "ok": true,
  "media_key": "tmdb:tv:1399",
  "generated_at": 1780660000000,
  "window_seconds": 86400,
  "watching_now": 23,
  "recent_watchers": 128,
  "recent_searches": 42,
  "recent_favorites": 8,
  "recent_following_adds": 5,
  "heat_score": 983.4,
  "display_text": "23 人正在播放"
}
```

Recommended status codes:

- `200 OK` with zero counts when the media exists but has no heat.
- `404 Not Found` is acceptable for unknown `media_key`; client treats it as no data.

Client behavior:

- If `display_text` is present, show it in the player detail area.
- Else if `watching_now > 0`, show `{watching_now} 人正在播放`.
- Else if `recent_watchers > 0`, show `{recent_watchers} 人近期观看`.
- Else hide the heat row.

## Event Triggers

- Global search submit: `search`.
- Recommendation card click: `search` with a context flag such as `source_kind = "heat_recommendation"`.
- Opening media detail where a stable media key exists: `detail_open`.
- Starting playback: `play_start`.
- Playback crosses effective-watch threshold: `watch_progress`.
- Adding favorite: `favorite_add`.
- Adding following: `following_add`.

Effective-watch threshold:

- First version: send once when playback reaches 10 minutes.
- For short media, allow `duration_seconds > 0` and `position_seconds >= duration_seconds * 0.3`.
- Send at most one effective `watch_progress` per media key per process session.

## UI Design

### Global Search Popup

Reuse the existing global search hot popup opened from the icon after the search field. Add a “大家在看” section above or beside existing hot keywords.

Recommended card fields:

- Poster
- Title
- Year/media type if available
- Heat reason, e.g. `128 人近期观看`

Click behavior:

- Fill global search with the item title and start global search.
- Do not add a new standalone detail page in first version.

### Player Detail Area

When current media has a media key, asynchronously call `/media/{media_key}`. If a displayable count exists, add a read-only detail row:

```text
热度: 23 人正在播放
```

No data means no row. Failures are silent.

## Privacy

Never send:

- Playback URL
- Original source URL
- Net disk share links
- Auth tokens
- Cookies
- Account name
- Password
- Raw plugin configuration
- HTTP headers used for playback

Allowed:

- Anonymous installation ID
- App/platform/version
- Media title and poster
- Stable public metadata IDs
- Coarse source kind such as `plugin`, `douban`, `following`, `favorite`
- Playback progress seconds without URL

## Error Handling

- Heat API failure must not block or change playback/search/favorite/following behavior.
- Requests run in background threads and return to UI via Qt signals.
- Log failures through the app log service or module logger.
- Keep UI empty when recommendations or media heat cannot be loaded.

## Testing

- HTTP client builds the exact `/events`, `/recommendations`, and `/media/{media_key}` calls.
- Event payload redacts playback URL, tokens, cookies, and headers.
- Recommendation response maps into UI card models.
- Empty and failed recommendation loads do not break the popup.
- Player detail heat row renders when `display_text`, `watching_now`, or `recent_watchers` exists.
- Player detail heat row is hidden for zero counts, `404`, timeout, and malformed responses.
- Search submit, recommendation click, favorite add, following add, playback start, and effective-watch progress trigger the correct event types.
- Effective-watch progress is sent at most once per media key per process session.
