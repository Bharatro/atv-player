# Playback Settings Tab Design

## Summary

在现有“高级设置”对话框已经包含 `元数据` 和 `网络代理` 两个 tab 的基础上，新增第三个 `播放设置` tab，用于承载少量高频、稳定、适合在播放器启动前决定的播放参数。

第一版目标：

- 新增 `播放设置` tab
- 提供 `YouTube Cookie` 浏览器来源下拉项
- 提供 `播放缓存大小（MB）`
- 提供 `解码模式`
- 提供 `网络超时`
- 提供 `普通流预读时长`
- 提供 `更多 MPV 配置` 多行文本输入

这轮重点不是把所有 `mpv` 参数都表单化，而是把最常调、最稳定、最不容易与播放窗口现有控制项重叠的配置提到高级设置里。

## Goals

- 用户可以在应用内持久化配置常用播放参数，而不是依赖环境变量或手工修改代码。
- 不重复暴露播放窗口里已经能实时控制的选项。
- 明确全局播放设置、特殊来源 profile 和 `更多 MPV 配置` 三者的优先级，避免行为混乱。
- 保持和当前配置体系一致：`AdvancedSettingsDialog -> AppConfig -> SettingsRepository -> mpv/yt-dlp runtime`。

## Non-Goals

- 本轮不把 `mpv` 所有参数都做成单独表单项。
- 本轮不新增截图配置。
- 本轮不重复添加播放窗口已经可调的项，例如最大音量、默认播放速度、自动加载字幕、字幕字体大小。
- 本轮不实现 `YouTube Cookie` 文本输入或 cookies 文件路径输入。
- 本轮不移除当前普通流、ISO、YouTube 的特殊 profile。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/player/mpv_widget.py`
- `src/atv_player/player/ytdlp_runtime.py`

主要验证：

- `tests/test_storage.py`
- `tests/test_main_window_ui.py`
- `tests/test_mpv_widget.py`
- `tests/test_ytdlp_runtime.py`

## Current Problem

当前播放器存在两个相关问题：

- 高级设置里还没有专门的播放参数入口，用户无法在应用内保存 `YouTube Cookie`、缓存、解码方式这类高频启动前参数。
- `mpv` 启动参数同时存在全局基础值和按来源切换的特殊 profile，如果直接往高级设置里追加字段但不定义优先级，后续行为会变得不可预测。

目前仓库中的播放侧逻辑已经有来源特化配置：

- 普通流使用默认 profile
- ISO 代理使用更低的预读和更激进的低延迟参数
- `yt-dlp` / DASH 代理使用更大的预读和不同的缓存等待策略

这意味着：

- 某些全局项适合直接暴露，例如缓存大小、解码模式、网络超时
- 某些项如果直接命名成“全局值”会和现有来源 profile 冲突，例如预读时长

## Approach Options

### Option A: Expose every requested field as a fully global value

做法：

- 所有表单项直接写成全局 `mpv` 启动参数
- 不区分普通流、ISO、YouTube 的现有特殊 profile

优点：

- 表面规则简单。

缺点：

- 会破坏当前已经存在的来源特化行为。
- `ISO` 和 `YouTube` 的启动体验容易回退。
- “预读时长”这类参数会和当前特殊 profile 直接冲突。

### Option B: Keep source-specific profiles and expose only stable global knobs

做法：

- 保留当前普通流 / ISO / `yt-dlp` 特殊 profile
- 只把不容易冲突的参数做成全局设置
- 将“预读时长”明确定义为“普通流预读时长”
- `更多 MPV 配置` 作为最终 override

优点：

- 最符合当前代码结构。
- 不会破坏已存在的来源特化逻辑。
- 用户仍有一个明确的高级兜底入口覆盖特殊需求。

缺点：

- 需要在 UI 或说明文案里写清优先级。

### Option C: Replace current profiles with a full profile editor

做法：

- 彻底重构当前 `mpv` profile 逻辑
- 让用户为普通流、ISO、YouTube 分别编辑独立配置

优点：

- 长期最灵活。

缺点：

- 复杂度明显超出本轮需求。
- UI、数据模型、测试范围都会大幅膨胀。

## Decision

采用 **Option B**。

原因：

- 现有播放器已经依赖来源特化 profile，第一版不应该推翻它。
- 用户当前要的是常用播放设置入口，而不是完整的 `mpv` profile 编辑器。
- 把 `更多 MPV 配置` 作为最终 override，可以兼顾“简单默认”和“高级可逃逸”。

## Design

### 1. Playback settings tab

在现有 `AdvancedSettingsDialog` 的 `QTabWidget` 中追加第三个 tab：

- `播放设置`

该 tab 包含以下表单项：

- `YouTube Cookie`
  - 控件：`QComboBox`
  - 选项：`不使用` / `Chrome` / `Edge` / `Firefox`
- `播放缓存大小（MB）`
  - 控件：整数输入
- `解码模式`
  - 控件：`QComboBox`
  - 选项：`硬解` / `软解`
- `网络超时`
  - 控件：整数输入
- `普通流预读时长`
  - 控件：整数输入
- `更多 MPV 配置`
  - 控件：`QPlainTextEdit`
  - 格式：每行一个 `key=value`
- 说明文案
  - 明确：`ISO / YouTube / DASH 等特殊来源仍会保留内置专用参数`
  - 明确：`更多 MPV 配置` 会在最后应用，并可覆盖同名基础项

### 2. Persisted config fields

在 `AppConfig` 中新增字段：

- `youtube_cookie_browser: str = ""`
- `mpv_cache_size_mb: int = 512`
- `mpv_hwdec_mode: str = "auto-safe"`
- `mpv_network_timeout_seconds: int = 15`
- `mpv_default_readahead_secs: int = 20`
- `mpv_extra_options: str = ""`

语义：

- `youtube_cookie_browser`
  - `""` 表示不使用
  - `"chrome"` / `"edge"` / `"firefox"` 表示对应浏览器来源
- `mpv_hwdec_mode`
  - `"auto-safe"` 表示硬解
  - `"no"` 表示软解

`SettingsRepository` 同步：

- 建表时增加对应列
- 老库迁移时补列
- `load_config()` / `save_config()` 支持完整 round-trip

### 3. Runtime wiring

#### `yt-dlp`

`YouTube Cookie` 只影响 `ytdlp_runtime`：

- 默认不传 `--cookies-from-browser`
- 用户显式选择浏览器时才传对应值

它不参与 `mpv` 的 profile 决策。

#### `mpv` base settings

以下字段作为全局基础值写入 `mpv` 初始化参数：

- `mpv_cache_size_mb` -> `demuxer_max_bytes`
- `mpv_hwdec_mode` -> `hwdec`
- `mpv_network_timeout_seconds` -> `network_timeout`
- `mpv_default_readahead_secs` -> 默认普通流的 `demuxer-readahead-secs`

#### source-specific profiles

保留现有来源特化 profile：

- 普通流：默认 profile
- ISO 代理：低延迟 profile
- `yt-dlp` / DASH：长预读 profile
- 分离音频流：低延迟 profile

关键规则：

- `普通流预读时长` 只覆盖普通流默认 profile 的 `demuxer-readahead-secs`
- ISO / `yt-dlp` / DASH 的专用 `readahead` 值继续由内置 profile 控制

### 4. Priority order

为避免冲突，运行时优先级固定为：

1. 内置基础启动参数
2. 高级设置中的基础播放项
3. 来源特化 profile 覆盖
4. `更多 MPV 配置` 最终覆盖

解释：

- 这样可以保留当前 ISO / `YouTube` 的特化行为
- 同时仍允许高级用户用 `更多 MPV 配置` 显式覆盖任何同名参数

### 5. Validation

保存前做轻量校验：

- `youtube_cookie_browser`
  - 仅允许 `"" / chrome / edge / firefox`
- `mpv_cache_size_mb`
  - 必须是正整数
  - 第一版建议限制在 `16 ~ 4096`
- `mpv_hwdec_mode`
  - 仅允许 `auto-safe / no`
- `mpv_network_timeout_seconds`
  - 必须是正整数
  - 第一版建议限制在 `1 ~ 300`
- `mpv_default_readahead_secs`
  - 必须是正整数
  - 第一版建议限制在 `1 ~ 600`
- `mpv_extra_options`
  - 忽略空行
  - 每行必须包含 `=`
  - `key` 不能为空

本轮不做：

- 完整 `mpv` 选项合法性校验
- 类型推断到所有可能的 `mpv` 值类型

## Data Flow

保存路径：

1. 用户在“高级设置 > 播放设置”修改表单
2. 点击保存
3. 对话框校验输入
4. 值写回 `AppConfig`
5. `save_config()` 持久化到 `app_config` 表

读取路径：

1. 应用启动或打开播放器时读取 `AppConfig`
2. `MpvWidget` 生成基础 `mpv` 参数
3. 根据 URL / 播放类型应用来源特化 profile
4. 最后合并 `更多 MPV 配置`

## Testing

需要补充或调整的测试：

- `tests/test_storage.py`
  - 新字段 round-trip
  - 默认值与旧库迁移行为正确
- `tests/test_main_window_ui.py`
  - 新 tab 存在且名称正确
  - 现有配置能正确回填
  - 保存后写回 `AppConfig`
  - 非法缓存值 / 非法 MPV 配置会阻止保存
- `tests/test_mpv_widget.py`
  - `hwdec` 会随配置切换
  - `demuxer_max_bytes` 会随缓存大小变化
  - 普通流预读时长会进入默认 profile
  - ISO / `yt-dlp` profile 仍保留各自专用 `readahead` 值
  - `更多 MPV 配置` 会覆盖基础项或 profile 项
- `tests/test_ytdlp_runtime.py`
  - 默认不传 `--cookies-from-browser`
  - 显式选择浏览器时传对应值

## Acceptance Criteria

- 高级设置中出现第三个 `播放设置` tab
- 用户可保存 `YouTube Cookie`、缓存大小、解码模式、网络超时、普通流预读时长和 `更多 MPV 配置`
- 默认情况下不再假设 `Chrome` cookies 来源
- 普通流会使用用户设置的默认预读时长
- ISO / `yt-dlp` / DASH 仍保留现有来源特化 `readahead` 行为
- `更多 MPV 配置` 作为最终 override 生效
