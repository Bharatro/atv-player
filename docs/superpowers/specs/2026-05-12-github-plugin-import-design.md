# GitHub Plugin Repository Import Design

## Summary

在插件管理中新增“从 GitHub 导入”入口。用户输入 GitHub 仓库地址后，应用自动识别仓库默认分支，下载该分支根目录下的 `spiders_v2.json`，把其中声明的插件批量导入为现有远程插件记录。

仓库导入仍复用当前远程插件模型：每个插件最终都保存为一个可直接下载源码的 raw URL。导入时会读取插件源码中的 `//@version:<n>`，并把版本保存到数据库；如果数据库中已存在相同 `source_value` 且版本相同的插件，则跳过导入。版本缺失或无法解析时默认按 `1` 处理。

## Goals

- 支持从 GitHub 仓库地址批量导入 TvBox Python 爬虫插件。
- 自动按仓库默认分支定位 `spiders_v2.json`。
- 把仓库条目转换为现有远程插件记录，不新增新的插件来源类型。
- 从插件源码读取 `//@version:<n>` 并保存到数据库。
- 对相同插件地址实现“同地址同版本跳过”。
- `spiders_v2.json` 中 `valid=false` 的插件默认导入为禁用。
- 导入过程中向用户显示可见进度。

## Non-Goals

- 支持非 GitHub 仓库或任意自定义 manifest 地址。
- 支持 `spiders_v2.json` 位于仓库子目录。
- 自动删除仓库中已移除的本地插件记录。
- 自动覆盖用户已经手动修改的启用状态、名称或配置文本。
- 引入后台同步或定时更新机制。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/plugins/repository.py`
- `src/atv_player/plugins/__init__.py`
- `src/atv_player/ui/plugin_manager_dialog.py`

主要验证：

- `tests/test_spider_plugin_manager.py`
- `tests/test_plugin_manager_dialog.py`

## Design

### User Flow

插件管理对话框新增一个“从 GitHub 导入”按钮。点击后弹出单行输入框，要求输入仓库地址，例如：

- `https://github.com/har01d5/tvbox`

输入有效地址后，对话框调用 `SpiderPluginManager` 新增的导入入口。导入结束后刷新插件列表，并向用户展示导入结果摘要，例如新增数、更新数、跳过数。

UI 只负责采集仓库地址、显示导入进度和展示结果，不在界面层做 GitHub 解析、manifest 解析或版本比较。

### Repository URL Resolution

管理层只接受标准 GitHub 仓库 URL，格式为：

- `https://github.com/<owner>/<repo>`
- 允许尾部 `/`

导入流程：

1. 解析出 `<owner>` 和 `<repo>`。
2. 读取该仓库的默认分支。
3. 拼出 `spiders_v2.json` 的 raw URL：
   - `https://raw.githubusercontent.com/<owner>/<repo>/<default_branch>/spiders_v2.json`
4. 下载并解析该 JSON 文件。

默认分支应通过仓库元数据自动发现，而不是硬编码 `main` 或 `master`。实现上可以通过 GitHub API 或仓库页面元数据完成，但对 manager 暴露的行为必须是“给定仓库 URL，自动找到默认分支”。

如果仓库地址格式不合法、仓库不存在、默认分支无法解析、或 `spiders_v2.json` 下载失败，manager 抛出明确错误，由 UI 负责弹窗展示。

### Manifest Contract

`spiders_v2.json` 顶层必须是数组。每个有效条目至少关心以下字段：

- `file`: 仓库内插件文件相对路径，例如 `py/双星.txt`
- `valid`: 可选布尔值；缺省按 `true` 处理

其他字段例如 `version` 不作为导入判定依据。真实版本以插件源码中的 `//@version:<n>` 为准，避免 manifest 声明与源码实际版本不一致。

无效条目处理规则：

- `file` 缺失、为空、或不是字符串：跳过
- `file` 不是相对路径：跳过
- 非数组顶层：报错，不继续导入

### Raw Plugin URL Mapping

每个 manifest 条目都转换成默认分支上的 raw 文件 URL：

- 仓库地址：`https://github.com/har01d5/tvbox`
- 默认分支：`master`
- `file`: `py/双星.txt`
- 生成：
  `https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E5%8F%8C%E6%98%9F.txt`

生成出的 raw URL 直接作为插件记录的 `source_value`，因此仓库导入后的插件与手动添加远程插件完全共用现有加载路径。

### Plugin Version Parsing

导入时需要先下载插件源码文本，并从源码中解析版本。版本规则：

- 识别形如 `//@version:6` 的声明
- 允许前后空白
- 建议只扫描源码前若干行，例如前 16 行，避免全文件正则搜索
- 解析失败、缺失、为空时默认版本为 `1`

版本信息保存到数据库字段 `plugin_version`，类型为整数，默认值为 `1`。

### Persistence Changes

`spider_plugins` 表新增：

- `plugin_version INTEGER NOT NULL DEFAULT 1`

`SpiderPluginConfig` 同步新增 `plugin_version: int = 1`。

repository 需要：

- 初始化新列和迁移老库
- `add_plugin(...)` 支持传入版本和默认启用状态
- `get_plugin()` / `list_plugins()` / `update_plugin()` 读写该字段
- 提供按 `source_value` 查找现有插件的方法，供 manager 做仓库导入去重

### Import Deduplication And Update Rules

批量导入针对“同一 raw URL”执行如下规则：

1. 数据库中不存在同 `source_value`
   - 新建插件记录
   - 默认名称取文件名 stem
   - `valid=false` 时默认 `enabled=false`
   - 其他情况默认 `enabled=true`
2. 数据库中已存在同 `source_value`，且现有 `plugin_version == 新版本`
   - 跳过，不新增重复记录
   - 不修改现有启用状态、显示名称、配置文本、排序
3. 数据库中已存在同 `source_value`，但版本不同
   - 更新现有记录的 `plugin_version`
   - 保留现有 `enabled`、`display_name`、`config_text`、`sort_order`
   - 不因为 manifest 的 `valid=false` 覆盖用户当前启用状态

这样可以避免重复导入同一版本，同时允许仓库后续版本升级时复用同一条插件记录。

### Refresh Behavior

新建插件记录后，沿用现有远程插件导入行为，立即执行一次刷新校验。这样可以尽早写入 `cached_file_path`、更新时间和加载错误。

版本升级命中已存在记录时，不需要在导入阶段额外改写 `source_value`，因为 URL 不变；但应触发一次刷新，让缓存源码与数据库记录保持一致。

### Progress Reporting

仓库导入至少包含默认分支解析、manifest 下载、逐个插件源码下载、数据库写入和插件刷新，因此 UI 必须显示导入进度，不能在整个过程中静默阻塞。

推荐交互：

- 导入开始后显示模态进度对话框
- 初始阶段显示“正在解析仓库信息”
- manifest 读取成功后切换为明确的分项进度，例如 `3 / 12`
- 当前消息可显示正在处理的文件名，例如 `正在导入 py/双星.txt`
- 导入完成或失败后关闭进度对话框

manager 通过纯 Python 回调向 UI 报告进度，不依赖 Qt 类型。每次进度回调至少包含：

- `stage`
- `current`
- `total`
- `message`

建议阶段值固定为：

- `resolve_repo`
- `fetch_manifest`
- `import_plugin`

首版不要求后台线程或取消按钮。允许同步执行，只要导入期间用户能持续看到进度更新。

### Result Reporting

manager 的仓库导入入口返回结构化结果，至少包含：

- `imported_count`
- `updated_count`
- `skipped_count`

UI 用该结果生成导入完成提示。

即使导入过程中已经显示了进度，最终提示仍然保留，用于总结实际结果。

### Error Handling

错误分两类：

- 整体错误：仓库 URL 非法、默认分支解析失败、manifest 下载/解析失败  
  直接终止并报错。
- 单条插件错误：某个 `file` 非法、某个源码下载失败、某个版本解析异常  
  跳过该条并继续导入其他条目，同时把该条计入跳过或失败摘要。

首版可以只在最终提示中显示总体摘要，不强制新增逐条失败日志 UI。

## Testing

需要覆盖：

- manager 能从 GitHub 仓库 URL 解析默认分支并读取 `spiders_v2.json`
- `valid=false` 导入后插件默认禁用
- 版本从源码 `//@version:<n>` 读取并保存
- 缺失版本声明时默认保存为 `1`
- 同 `source_value` 且同版本时跳过
- 同 `source_value` 但版本变化时更新版本并保留用户现有启用状态
- 对话框新增 GitHub 导入按钮，并把仓库 URL 交给 manager
- 对话框在导入期间显示进度，并随着 manager 回调更新状态

## Open Questions

无。当前范围内的行为已经固定：

- 默认分支自动发现
- `spiders_v2.json` 固定在仓库根目录
- 版本以源码 `//@version:` 为准
- 默认版本为 `1`
- 同地址同版本跳过
- 导入期间显示进度
