# yt-dlp Cookies Browser Setting Design

## Summary

为桌面播放器新增“高级设置 > yt-dlp Cookies 来源浏览器”配置项，让用户可以在应用内显式选择 `yt-dlp` 的浏览器 cookies 来源，而不是依赖环境变量或默认假设 `Chrome`。

第一版目标：

- 在高级设置窗口新增 `yt-dlp Cookies 来源浏览器` 下拉项
- 将该配置纳入 `AppConfig` 和 `SettingsRepository` 持久化
- 默认值为 `不使用`
- `yt-dlp` 运行时仅在用户显式选择浏览器时才追加 `--cookies-from-browser`

这轮重点是修正“Windows 未安装 Chrome 时，默认播放 YouTube 失败”的默认行为，并给用户一个明确、可持久化的开关。

## Goals

- 用户可以在应用内直接控制 `yt-dlp` 是否使用浏览器 cookies。
- 默认安装后的行为不再假设系统存在 `Chrome`。
- 已有配置链路保持一致：`AdvancedSettingsDialog -> AppConfig -> SettingsRepository -> ytdlp runtime`。
- 为后续补充更多浏览器选项保留清晰扩展位。

## Non-Goals

- 不支持应用层 `cookies` 文件路径。
- 本轮不实现“自动探测系统可用浏览器”。
- 本轮不新增 `yt-dlp` 专用诊断面板或错误提示优化。
- 本轮不保留“默认隐式回退到 Chrome”的旧行为。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/player/ytdlp_runtime.py`

主要验证：

- `tests/test_storage.py`
- `tests/test_main_window_ui.py`
- `tests/test_ytdlp_runtime.py`
- 按需补充 `tests/test_yt_dlp_service.py`

## Current Problem

当前 `yt-dlp` cookies 逻辑存在两个问题：

- 高级设置窗口没有任何对应配置项，用户只能依赖环境变量控制行为。
- `ytdlp_runtime` 在未显式配置时默认回退到 `chrome`，会自动传入 `--cookies-from-browser chrome`。

这会直接导致一个明显的问题：

- 在 Windows 未安装 Chrome 的机器上，`yt-dlp` 会尝试访问 `Chrome` 的 cookies 数据目录并报错。
- 即使目标 YouTube 视频本身是公开可播放的，也会先因为默认 cookies 来源不存在而失败。

## Approach Options

### Option A: Keep environment variables as the primary source and only add UI glue

做法：

- 高级设置窗口新增下拉框
- 保存时只改写环境变量，不进入 `AppConfig`

优点：

- 表面改动较小。

缺点：

- 和现有应用配置体系割裂。
- 重启、生效时机和持久化语义都不清晰。
- 后续继续扩展 `yt-dlp` 相关设置时会越来越混乱。

### Option B: Add a persisted AppConfig field and have runtime read that value

做法：

- 在 `AppConfig` 中新增 `yt_dlp_cookies_browser`
- 高级设置直接编辑该字段
- `ytdlp_runtime` 只根据该配置决定是否追加 `--cookies-from-browser`

优点：

- 与现有设置模型一致。
- 默认值和持久化行为清晰。
- 最直接修复“默认假设 Chrome”导致的失败。

缺点：

- 需要补充模型、存储和测试。

### Option C: Add automatic browser detection

做法：

- UI 提供 `自动` 模式
- 运行时尝试探测本机可用浏览器并自动选择

优点：

- 理论上对一部分用户更省事。

缺点：

- 复杂度明显上升。
- 需要处理不同平台、不同 profile 路径和失败回退语义。
- 不适合作为这次最小修复。

## Decision

采用 **Option B**。

原因：

- 这次需求明确要求在高级设置窗口增加配置项，而不是继续依赖外部环境变量。
- `AppConfig` 持久化方式与项目现有模式一致，风险最低。
- 默认值设为 `不使用` 后，可以直接修复“Windows 没装 Chrome 也被默认强制走 Chrome cookies”的问题。

## Design

### 1. AppConfig and persistence

在 `AppConfig` 中新增字段：

- `yt_dlp_cookies_browser: str = ""`

语义：

- `""` 表示 `不使用`
- `"chrome"` 表示 `Chrome`
- `"edge"` 表示 `Edge`
- `"firefox"` 表示 `Firefox`

`SettingsRepository` 同步：

- 初始化建表时新增 `yt_dlp_cookies_browser TEXT NOT NULL DEFAULT ''`
- 老库迁移时补列
- `load_config()` / `save_config()` 支持完整 round-trip

默认值：

- 所有新配置和老库迁移后的默认值都为 `''`
- 这意味着应用默认不向 `yt-dlp` 追加 `--cookies-from-browser`

### 2. Advanced settings dialog

在 [src/atv_player/ui/advanced_settings_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/advanced_settings_dialog.py) 中新增一个下拉框：

- 标签：`yt-dlp Cookies 来源浏览器`
- 控件：`QComboBox`
- 选项：
  - `不使用`
  - `Chrome`
  - `Edge`
  - `Firefox`

值映射：

- `不使用` -> `""`
- `Chrome` -> `"chrome"`
- `Edge` -> `"edge"`
- `Firefox` -> `"firefox"`

行为：

- 打开对话框时，根据 `config.yt_dlp_cookies_browser` 选择当前项
- 点击保存时，将当前选项写回 `config.yt_dlp_cookies_browser`
- 点击取消时不落盘

本轮不做：

- 文件选择器
- 自动探测浏览器
- 复杂联动说明文案

### 3. Runtime behavior

`src/atv_player/player/ytdlp_runtime.py` 的 cookies 决策逻辑改为：

- 如果显式配置了浏览器值，则返回该浏览器
- 如果显式关闭，则返回空字符串
- 如果没有配置任何浏览器，则默认也返回空字符串
- 不再支持应用层 cookie 文件入口，cookie 只由 yt-dlp 的浏览器参数自行处理

结果：

- 默认情况下不再生成 `--cookies-from-browser chrome`
- 只有用户显式在高级设置里选择浏览器后，才会生成对应参数

兼容性：

- 如果代码里仍保留环境变量兼容逻辑，配置优先级应以应用内持久化配置为主
- 但第一版不需要引入复杂优先级系统；只要确保默认行为不再隐式回退到 `chrome`

### 4. Error handling

这次不新增新的 UI 提示机制。

行为约束：

- 如果用户显式选择了 `Chrome`，但系统未安装 Chrome，`yt-dlp` 继续报原始错误
- 这属于用户主动选择后的可预期失败，不再是默认配置导致的陷阱
- 如果用户选择 `不使用`，则不应再出现“找不到 Chrome cookies 数据库”的默认失败

## Data Flow

保存路径：

1. 用户在高级设置对话框选择 `yt-dlp Cookies 来源浏览器`
2. 点击保存
3. 对话框将值写回 `AppConfig.yt_dlp_cookies_browser`
4. `save_config()` 持久化到 `app_config` 表

读取路径：

1. 应用启动或运行时读取 `AppConfig`
2. `ytdlp_runtime` 根据配置值决定是否追加 `--cookies-from-browser`
3. `yt_dlp_service` / mpv `ytdl` 相关调用沿用现有命令构造路径

## Testing

需要补充或调整的测试：

- `tests/test_storage.py`
  - 新字段可持久化 round-trip
  - 旧值为空时加载为 `''`
- `tests/test_main_window_ui.py`
  - 高级设置对话框能加载现有浏览器选项
  - 保存后会写回 `config.yt_dlp_cookies_browser`
- `tests/test_ytdlp_runtime.py`
  - 默认情况下不再返回 `chrome`
  - 显式设置 `chrome` / `edge` / `firefox` 时生成对应参数
  - `不使用` 时不生成 `--cookies-from-browser`

## Acceptance Criteria

- 默认配置下，`build_ytdlp_command_args()` 不再包含 `--cookies-from-browser`
- 高级设置窗口可选择 `不使用` / `Chrome` / `Edge` / `Firefox`
- 保存后重启应用仍能保留该选择
- 当值为 `不使用` 时，Windows 无 Chrome 的环境不会因为默认 cookies 来源而失败
- 当值为 `Chrome` 等具体浏览器时，仍保持显式传参行为
