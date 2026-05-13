# Spider Plugin Detail Grouped Sources Design

## Summary

为爬虫插件 `detailContent()` 增加一个可选的 `group` 返回字段，用来显式表达播放器需要的两级来源分组。只要 `group` 非空且能解析出有效内容，播放器就完全使用 `group` 构建来源分组，不再依赖 `vod_play_from` 和 `vod_play_url` 的命名约定；只有 `group` 缺失、为空、格式非法或解析后没有任何有效来源时，才回退到旧字段解析逻辑。

## Goals

- 让插件显式返回两级来源分组，而不是依赖 `解析1`、`百度2` 这类线路名推断。
- 让 `group[].name` 直接映射为一级分组名。
- 让 `group[].media[]` 每项映射为一个叶子子源。
- 保持老插件完全兼容，不要求立刻改写现有 `vod_play_from` / `vod_play_url`。

## Non-Goals

- 不支持 `group` 内再嵌套更深层级。
- 不在这次设计里扩展 `media` 为多集播放列表。
- 不同时合并展示 `group` 和 `vod_play_from` / `vod_play_url` 两套来源。

## Schema

`detailContent()` 返回值示例：

```json
{
  "list": [
    {
      "vod_id": "detail-1",
      "vod_name": "影视标题",
      "group": [
        {
          "name": "百度",
          "media": [
            {
              "name": "影视标题1",
              "url": "https://pan.baidu.com/s/xxx"
            }
          ]
        },
        {
          "name": "夸克",
          "media": [
            {
              "name": "影视标题10",
              "url": "https://pan.quark.cn/s/xxx"
            }
          ]
        }
      ]
    }
  ]
}
```

字段约束：

- `group`
  - 类型：`list`
  - 语义：一级来源分组列表
- `group[].name`
  - 类型：`string`
  - 语义：一级分组显示名，例如 `百度`、`夸克`
- `group[].media`
  - 类型：`list`
  - 语义：该一级分组下的叶子子源列表
- `group[].media[].name`
  - 类型：`string`
  - 语义：叶子子源显示名
- `group[].media[].url`
  - 类型：`string`
  - 语义：该叶子子源对应的播放目标，可以是网盘链接、页面链接或直链媒体 URL

## Parsing Rules

解析入口仍然在 `SpiderPluginController.build_request()`。

处理顺序：

1. 读取 `raw_detail.get("group")`
2. 如果 `group` 是非空列表，并且能解析出至少一个有效 `media.url`，则使用 `group`
3. 否则回退到现有 `vod_play_from` / `vod_play_url` 解析逻辑

`group` 解析规则：

- 非 `dict` 的 group 项忽略
- `group[].name` 为空时，该 group 项忽略
- `group[].media` 非 `list` 时，该 group 项忽略
- `media` 中非 `dict` 的项忽略
- `media[].name` 为空时，用 `media[].url` 作为显示名
- `media[].url` 为空时，该 media 项忽略
- 一个 group 解析后没有任何有效 media，则整个 group 忽略
- 所有 group 都被忽略时，视为 `group` 无效，回退到旧字段

## Mapping To Player Sources

每个有效 `group` 映射为一个 `PlaybackSourceGroup`：

- `PlaybackSourceGroup.label = group[].name`

每个有效 `media` 映射为一个 `PlaybackSource`：

- `PlaybackSource.label = media[].name`，为空则退到 `media[].url`

每个 `PlaybackSource` 的初始 `playlist` 只有一个 `PlayItem`：

- `PlayItem.title = media[].name`，为空则退到 `media[].url`
- `PlayItem.media_title = detail.vod_name`
- `PlayItem.play_source = media[].name` 或退回的显示名
- `PlayItem.index = 0`
- 如果 `media[].url` 已是直链媒体 URL：
  - `PlayItem.url = media[].url`
  - `PlayItem.vod_id = ""`
- 如果 `media[].url` 不是直链媒体 URL，例如网盘分享链接、页面链接：
  - `PlayItem.url = ""`
  - `PlayItem.vod_id = media[].url`

这让现有播放 loader、网盘详情替换、解析逻辑继续沿用当前 `PlayItem.url` / `PlayItem.vod_id` 语义。

## Fallback Rules

回退条件必须严格且单向：

- `group` 缺失：回退
- `group` 为空列表：回退
- `group` 不是列表：回退
- `group` 解析后没有任何有效 group/source：回退

一旦 `group` 解析出至少一个有效叶子子源：

- 完全忽略 `vod_play_from`
- 完全忽略 `vod_play_url`

不做混合补齐，不做双路并存。

## Compatibility

老插件继续只返回：

- `vod_play_from`
- `vod_play_url`

则行为保持不变，仍走现有旧解析路径。

新插件可以只返回 `group`，不填 `vod_play_from` / `vod_play_url`。

也可以同时返回两套字段，但由于优先级规则明确，只要 `group` 有效，就只使用 `group`。

## Testing

测试应覆盖：

- `group` 有效时构建两级来源分组
- `group` 有效时忽略 `vod_play_from` / `vod_play_url`
- `group` 中部分项非法时跳过非法项，保留有效项
- `group` 完全无效时回退旧字段
- `media.url` 为直链时直接填 `PlayItem.url`
- `media.url` 为网盘或页面链接时填 `PlayItem.vod_id`

## Result

完成后，爬虫插件可以通过 `detailContent().group` 直接返回播放器所需的两级来源分组。新插件不必再通过线路命名约定暗示分组结构；老插件则继续使用 `vod_play_from` 和 `vod_play_url`，不受影响。
