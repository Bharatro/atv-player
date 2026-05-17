# Metadata ID Link Styling Design

## Summary

优化播放器详情区中的元数据外链字段，把 `IMDb ID`、`TMDB ID`、`豆瓣ID`、`Bangumi ID` 统一渲染为可点击链接，并给这些 ID 链接增加更清晰但轻量的视觉样式。

本次改动只影响播放器详情 HTML 渲染层，不调整元数据抓取、合并或 `PlaybackDetailField` 的数据结构。

## Goals

- 为 `IMDb ID` 增加通用外链映射，目标地址为 `https://www.imdb.com/title/<id>`
- 保持 `TMDB ID`、`豆瓣ID`、`Bangumi ID` 的现有通用映射能力
- 统一这些元数据 ID 外链的显示样式，让用户更容易识别可点击字段
- 保持现有内部动作链接和普通元数据文本的行为不变

## Non-Goals

- 不修改 metadata provider 的抓取逻辑
- 不新增新的元数据字段类型
- 不重做详情页整体排版
- 不调整简介区中的普通富文本链接样式

## Scope

主要修改文件：

- `src/atv_player/ui/player_window.py`
- `tests/test_player_window_ui.py`

文档文件：

- `docs/superpowers/specs/2026-05-17-metadata-id-link-styling-design.md`
- `docs/superpowers/plans/2026-05-17-metadata-id-link-styling.md`

## URL Mapping

`PlayerWindow._external_metadata_url()` 继续作为统一出口，规则如下：

- `豆瓣ID` / `dbid` -> `https://movie.douban.com/subject/<id>/`
- `Bangumi ID` -> `https://bgm.tv/subject/<id>`
- `TMDB ID` -> 继续根据 `target` 或 `infer_tmdb_media_type(...)` 推断 `movie` / `tv`
- `IMDb ID` -> `https://www.imdb.com/title/<id>`

如果字段值本身已经是 `http://` 或 `https://`，继续直接返回原始 URL。

## Rendering Approach

详情页当前通过 `QTextBrowser` + HTML 渲染 metadata。

本次继续沿用现有方式，只在生成 HTML 时区分“外部元数据 ID 链接”和其他文本：

- 普通文本：保持原样
- 内部动作链接（`atv-player://detail-field?...`）：保持现有 `<a>` 输出
- 外部元数据 ID 链接：使用统一 class 输出，附带更明确的颜色、下划线和悬停样式

推荐样式方向：

- 基础颜色略高于正文对比度
- 默认带下划线，明确这是链接
- 悬停时加深颜色
- 不引入按钮感、边框或块级胶囊样式，避免喧宾夺主

## Styling Boundary

样式只覆盖通过 `_external_metadata_url()` 识别出的元数据外链，不覆盖：

- 简介正文中的普通 HTML 链接
- 由 `_render_metadata_value_html()` 生成的内部动作链接
- 非 ID 类型的普通详情行

这样可以保证“能跳到外部站点的元数据 ID”有统一样式，同时不破坏已有细粒度交互。

## Error Handling

- 若字段值为空，继续不生成链接
- 若字段不在已知映射范围内，继续按纯文本输出
- 点击外部链接仍然走 `_handle_metadata_link()` 和 `QDesktopServices.openUrl()`
- 打开失败时继续沿用现有日志提示

## Testing Strategy

在 `tests/test_player_window_ui.py` 增加或扩展回归测试：

- `IMDb ID` 会被渲染为 `https://www.imdb.com/title/<id>`
- 已知的 `TMDB ID`、`豆瓣ID`、`Bangumi ID` 仍然渲染为正确 URL
- 外部元数据 ID 链接 HTML 带有统一样式 class
- 直接点击外部链接仍然会调用 `QDesktopServices.openUrl()`

## Risks

- `QTextBrowser.toHtml()` 可能会对输入 HTML 做规范化，测试不能依赖完整原始字符串顺序
- 样式若写在每个链接内联属性里，会让 HTML 断言脆弱，因此更适合用 class 名做测试锚点
