# YouTube Max Quality Cap Design

**Goal**

在“高级设置 > 播放设置”增加一个全局配置，用来限制 YouTube 默认解析的最高画质，降低首次播放和恢复播放时误入 4K/DASH 的概率，同时不影响播放中的手动降档切换。

**Scope**

- 增加全局配置字段 `youtube_max_height`
- 在高级设置播放页增加“ YouTube 最高画质”下拉框
- 持久化到本地设置数据库
- 让 `yt_dlp_service` 在未显式指定 `max_height` 时默认读取该配置

**Out of Scope**

- 不修改播放器内现有手动切换清晰度的交互
- 不新增“突破上限”的临时覆盖入口
- 不处理 DASH 启播慢的 seek 时序问题

**Behavior**

- 默认值为 `0`，表示不限制
- 可选值：`0 / 480 / 720 / 1080 / 1440 / 2160`
- 初次解析 YouTube URL、以及未显式指定画质的重新解析，使用该上限
- 播放器内用户手动切到更低画质，仍按现有逻辑工作

**Architecture**

- `AppConfig` 承载配置
- `AdvancedSettingsDialog` 提供设置入口并校验
- `SettingsRepository` 负责字段迁移、加载和保存
- `YtdlpService` 读取配置作为默认 `max_height`

**Testing**

- 设置对话框保存后，配置写入 `youtube_max_height`
- 设置仓库能对新字段做默认值、归一化和持久化
- `YtdlpService.resolve()` 在未显式传入 `max_height` 时会使用配置值
- 配置为 `0` 时保留不限制行为
