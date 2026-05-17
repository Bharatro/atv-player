# GitHub Plugin Import Manifest Version Design

## Summary

将“从 GitHub 导入”里的版本来源从插件源码 `//@version:` 切换为 `spiders_v2.json` 条目的 `version` 字段。导入时以 manifest 版本作为唯一判定依据：同一 `source_value` 且版本未变化时跳过，版本变化时更新现有记录并刷新插件。

## Goals

- 从 `spiders_v2.json[].version` 读取 GitHub 导入插件版本。
- 忽略版本没有变化的插件。
- 保持现有 `valid=false` 首次导入默认禁用行为。
- 保持现有远程插件存储模型和刷新流程。

## Non-Goals

- 不修改手动添加远程插件或本地插件的版本规则。
- 不新增新的插件来源类型。
- 不改变 `source_value` 去重方式。
- 不新增后台任务或自动同步。

## Design

### Manifest Contract

`spiders_v2.json` 顶层必须是数组。每个有效条目关心以下字段：

- `file`: 仓库内插件文件相对路径
- `valid`: 可选布尔值；缺省按 `true` 处理
- `version`: 必填整数；用于 GitHub 导入版本判定

条目处理规则：

- `file` 缺失、为空、非字符串、绝对路径或包含 `..`：跳过
- `version` 缺失、为空、非整数、或整数小于 `1`：跳过
- 单条插件源码下载失败：跳过该条，继续后续导入
- 顶层不是数组：整体报错并终止导入

### Version Source

GitHub 导入只认 manifest 的 `version` 字段。插件源码中的 `//@version:` 不再参与 GitHub 导入的新增、更新或跳过判定。

数据库里的 `plugin_version` 继续复用，语义调整为“最近一次 GitHub 导入时记录的 manifest 版本”。

### Deduplication And Update Rules

针对每个由 manifest 转换出的 raw URL：

1. 数据库中不存在相同 `source_value`
   - 新建远程插件记录
   - `plugin_version` 保存 manifest `version`
   - `valid=false` 时默认 `enabled=false`
2. 数据库中已存在相同 `source_value` 且 `plugin_version == manifest version`
   - 跳过
   - 不刷新、不覆盖用户配置
3. 数据库中已存在相同 `source_value` 且版本不同
   - 更新 `plugin_version`
   - 保留 `display_name`、`enabled`、`config_text`、`sort_order`
   - 执行一次刷新，拉取新源码

### Compatibility

旧数据不做迁移清洗。已有插件记录中的 `plugin_version` 可能来自旧的源码版本规则，但下一次 GitHub 导入时会自然收敛到新的 manifest 版本规则：

- 若旧值与 manifest `version` 相同，则直接跳过
- 若不同，则更新为 manifest `version` 并刷新

## Testing

需要覆盖：

- 版本从 `spiders_v2.json[].version` 读取并保存
- 源码 `//@version:` 与 manifest 不一致时，以 manifest 为准
- 同 `source_value` 且版本未变时跳过
- 同 `source_value` 且版本变化时更新并保留用户配置
- `version` 缺失或非法时跳过
