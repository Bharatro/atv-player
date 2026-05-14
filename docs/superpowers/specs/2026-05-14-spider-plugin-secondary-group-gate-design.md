# Spider Plugin Secondary Group Gate Design

## Summary

播放器里的二级来源分组只能由爬虫插件 `detailContent()` 返回的 `group` 字段显式开启。`group` 只要缺失、为空、格式非法，或解析后没有任何有效来源，播放器就回退到旧的 `vod_play_from` / `vod_play_url` 播放列表解析逻辑，但不再基于旧字段推导二级分组结构。

## Goals

- 明确二级分组的唯一开关是 `group`。
- 保持老插件的播放列表解析兼容，不破坏 `vod_play_from` / `vod_play_url` 现有播放能力。
- 禁止旧字段命名约定继续隐式触发二级分组 UI。

## Non-Goals

- 不改变 `group` 有效时的两级分组结构。
- 不改变老字段生成多个播放列表的能力。
- 不在这次调整里重写旧字段的选集解析规则。

## Behavior

处理顺序保持不变：

1. 先读取 `raw_detail.get("group")`
2. 如果 `group` 可解析出至少一个有效叶子子源，则：
   - 使用 `group` 构建 `source_groups`
   - 使用 `group` 构建 `playlists`
3. 否则：
   - 使用 `vod_play_from` / `vod_play_url` 构建 `playlists`
   - `source_groups` 保持为空

这意味着：

- `group` 存在且有效：开启二级分组
- `group` 不存在：不开启二级分组
- `group` 存在但无效：不开启二级分组

## Implementation Notes

`SpiderPluginController.build_request()` 继续先尝试 `_build_grouped_sources_from_payload()`。

当 `group` 无法产出任何有效 `playlists` 时，控制器仍调用旧的 `_build_playlist()`，但不再调用 `_build_source_groups_from_playlists()` 依据 `play_source` 文本推导 `PlaybackSourceGroup`。

这样可以保留：

- 老插件的多线路、多播放列表行为
- 现有播放加载、网盘替换、历史记录索引语义

同时去掉：

- `解析1`、`解析2`
- `百度1`、`百度2`

这类旧线路命名对二级分组 UI 的隐式驱动。

## Testing

测试应覆盖：

- `group` 有效时仍构建二级分组
- `group` 缺失时只构建旧播放列表，不构建 `source_groups`
- `group` 无效时只构建旧播放列表，不构建 `source_groups`
- 老字段多线路回退时仍保留多个 `playlists`

## Result

完成后，播放器只会在插件显式返回有效 `group` 时显示二级来源分组。旧插件仍可通过 `vod_play_from` / `vod_play_url` 提供多线路播放，但不会再因为线路名称格式而自动进入二级分组模式。
