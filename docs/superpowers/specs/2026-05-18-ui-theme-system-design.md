# UI Theme System Design

## Summary

为 `atv-player` 引入统一主题系统，解决当前 `QSS` 和控件配色分散、跨平台视觉不一致的问题。

第一版主题系统目标：

- 提供 `浅色` / `深色` / `跟随系统` 三档主题模式
- `跟随系统` 只在应用启动时读取系统当前浅深色，不做运行中监听
- 通过统一 `ThemeManager` 管理应用 palette、全局 `QSS` 和主题 token
- 覆盖所有顶层窗口和主要弹窗
- `PlayerWindow` 采用混合方案：
  - 外围 UI 跟随全局主题
  - 视频播放区域、控制层、悬浮层保持偏暗沉浸

这轮重点不是一次性重写全部 UI，而是先建立稳定的主题底座，并将主要窗口、主要弹窗、播放器外围区域收敛到统一主题体系。

## Goals

- 为 `Linux KDE`、`GNOME`、`Windows`、`macOS` 提供更统一的应用级视觉表现。
- 消除主要窗口和主要弹窗中分散的硬编码颜色，改为统一主题 token。
- 在 `AdvancedSettingsDialog` 中提供明确的主题入口，并持久化用户选择。
- 保证 `PlayerWindow` 在支持浅/深主题的同时，不牺牲媒体播放器的暗场沉浸感。
- 为后续支持“运行中跟随系统变化”预留清晰扩展点，但本轮不实现。

## Non-Goals

- 本轮不实现系统主题变化监听，也不在应用运行中自动切换主题。
- 本轮不追求把所有零散 `QSS` 一次性完全重写干净。
- 本轮不引入“跟随系统强调色”或平台原生强调色方案。
- 本轮不让 `PlayerWindow` 的视频区域在浅色主题下真正切换为浅底。
- 本轮不为了主题系统重构页面布局或交互逻辑。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/app.py`
- `src/atv_player/ui/theme.py`（新增）
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/ui/login_window.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/ui/history_page.py`
- `src/atv_player/ui/poster_grid_page.py`
- `src/atv_player/ui/plugin_manager_dialog.py`
- `src/atv_player/ui/live_source_manager_dialog.py`
- `src/atv_player/ui/player_window.py`

主要验证：

- `tests/test_storage.py`
- `tests/test_app.py`
- `tests/test_main_window_ui.py`
- `tests/test_player_window_ui.py`
- 需要时新增 `tests/test_theme.py`

## Current Problem

当前 UI 视觉存在几个直接问题：

- 主题能力缺失，应用无法表达 `浅色` / `深色` / `跟随系统` 的用户偏好。
- 颜色和样式散落在多个页面的局部 `QSS` 中，难以统一维护。
- 不同平台对默认控件 palette 的处理不同，导致 KDE、GNOME、Windows、macOS 观感越来越分叉。
- 播放器、设置弹窗、主窗口之间缺少统一的视觉层级，整体像多个风格不一致的子系统拼在一起。

当前代码已经有明显的局部硬编码：

- `MainWindow` 中的容器、标签、搜索框、历史项、热搜项等 `QSS`
- `PosterGridPage` 的筛选按钮、局部标签颜色
- `HistoryPage` 的搜索框和按钮
- `PluginManagerDialog` 的 placeholder action 样式
- `PlayerWindow` 的局部按钮和颜色逻辑

如果继续在现有模式上叠加新页面或新控件，主题相关判断和硬编码颜色只会持续扩散。

## Approach Options

### Option A: Full strict follow for every window including player

做法：

- `ThemeManager` 统一决定浅/深主题
- 所有窗口，包括 `PlayerWindow` 全部严格切换到对应浅/深色表达

优点：

- 规则最简单
- 主题系统实现路径最直接

缺点：

- 浅色 `PlayerWindow` 往往会损伤观影场景的沉浸感
- 媒体播放器核心区域不适合完全浅底化

### Option B: Global theme plus immersive dark player layer

做法：

- 全局主题支持 `light | dark | system`
- `system` 在应用启动时解析成实际主题
- `LoginWindow`、`MainWindow`、主要弹窗、`PlayerWindow` 外围 UI 跟随全局主题
- `PlayerWindow` 的视频区、底部控制层、悬浮层保持偏暗沉浸

优点：

- 最符合媒体类桌面应用的视觉规律
- 兼顾跨平台统一性和播放器体验
- 后续扩展为运行中跟随系统变化时也不需要改动各个窗口职责

缺点：

- 主题规则比“全窗口完全一致”多一层播放器特例

### Option C: Keep player permanently independent and dark

做法：

- 主窗口和弹窗进入主题系统
- `PlayerWindow` 完全独立，始终深色

优点：

- 播放器观感最稳定

缺点：

- 产品割裂感最强
- 用户切换主题时，播放器像进入另一个应用

## Decision

采用 **Option B**。

原因：

- 用户明确要求 `PlayerWindow` 使用“混合方案：播放器播放区默认偏暗”。
- 这也是更成熟的媒体类桌面应用做法：统一主题系统，但保护播放区沉浸感。
- `follow-system` 只在启动时解析，已经足以覆盖当前跨平台一致性诉求，同时实现复杂度可控。

## Design

### 1. Theme mode model

在 `AppConfig` 中新增：

- `theme_mode: str = "system"`

合法值：

- `"light"`
- `"dark"`
- `"system"`

语义：

- `light`: 强制浅色
- `dark`: 强制深色
- `system`: 应用启动时读取系统当前主题，并解析为实际浅/深色

`SettingsRepository` 负责：

- 建表时增加 `theme_mode`
- 老库迁移时补列
- `load_config()` / `save_config()` 支持 round-trip
- 非法值统一回退到 `"system"`

### 2. ThemeManager

新增 `src/atv_player/ui/theme.py`，作为唯一主题入口。

包含以下核心结构：

- `ThemeMode`
  - 表示用户偏好：`light` / `dark` / `system`
- `ResolvedTheme`
  - 表示实际生效主题：`light` / `dark`
- `ThemeTokens`
  - 统一承载主题 token
- `ThemeManager`
  - 从 `AppConfig` 读取主题偏好
  - 解析系统当前浅/深色
  - 生成 palette、全局 `QSS`、页面级 token
  - 提供播放器沉浸层 token

`ThemeManager` 对外职责：

- `resolve_theme(mode) -> ResolvedTheme`
- `build_palette(theme) -> QPalette`
- `build_application_stylesheet(theme) -> str`
- `theme_tokens(theme) -> ThemeTokens`
- `player_tokens(theme) -> ThemeTokens` 或等价接口

原则：

- 所有页面只消费“已经解析好的主题”和 token
- 页面自身不判断系统浅深色
- 页面级代码不直接写品牌色和背景色常量

### 3. Resolving system theme

`follow-system` 的解析规则：

- 仅在应用启动时执行一次
- 优先读取 Qt 能提供的系统颜色方案
- 如果平台没有给出明确结果，则回退到 `light`

第一版不做：

- 系统主题变化监听
- 已打开窗口自动跟随系统实时变化

后续若要支持运行中跟随系统变化，只增强 `ThemeManager` 即可，不改变窗口接入方式。

### 4. Theme tokens

主题系统不再让页面直接使用具体颜色值，而是统一使用语义 token。

至少包含以下 token：

- `window_bg`
- `panel_bg`
- `panel_alt_bg`
- `border_subtle`
- `border_strong`
- `text_primary`
- `text_secondary`
- `text_muted`
- `accent`
- `accent_hover`
- `accent_pressed`
- `selection_bg`
- `selection_text`
- `input_bg`
- `input_border`
- `input_focus_border`
- `button_bg`
- `button_hover_bg`
- `button_primary_bg`
- `button_primary_text`
- `danger_bg`

`PlayerWindow` 额外需要沉浸层 token：

- `player_overlay_bg`
- `player_controls_bg`
- `player_scrim`
- `player_text_on_dark`
- `player_border_on_dark`

品牌策略：

- 使用固定应用品牌色，不跟随系统强调色
- 浅色和深色都复用同一品牌色家族，但调整亮度和透明度层级

### 5. Application-wide installation

在 `build_application()` 中初始化主题系统。

流程：

1. 创建 `QApplication`
2. 加载 `AppConfig`
3. 创建 `ThemeManager`
4. 解析当前生效主题
5. 对 `QApplication` 安装：
   - palette
   - 全局 stylesheet
   - 主题相关运行时状态（如需要）

保存主题设置后：

- 立即重新应用当前 palette 和全局 `QSS`
- 已打开的主要窗口和主要弹窗应该直接体现新主题
- 若选择 `system`，则按“当前系统主题”立即解析一次，而不是等到下次重启

说明：

- `system` 的“跟随”语义针对的是“按系统决定当前主题”
- 但第一版依然不负责监听系统后续变化

### 6. AdvancedSettingsDialog appearance tab

在现有 `AdvancedSettingsDialog` 中新增独立“外观”页，作为主题入口。

建议结构：

- 新增 tab：`外观`
- 主题模式控件：
  - `浅色`
  - `深色`
  - `跟随系统`
- 可选说明文案：
  - `跟随系统会在应用启动时读取当前系统浅深色`
  - `播放器播放区会保持偏暗，以获得更好的沉浸感`

保存行为：

- 保存时更新 `AppConfig.theme_mode`
- 调用统一的主题应用入口立即刷新 UI

视觉方向：

- 采用统一应用级视觉风格，而不是尽量贴近原生平台控件配色
- 使用统一品牌色、统一圆角、统一卡片和输入框层级

### 7. Window adoption rules

#### LoginWindow

- 完全跟随全局主题
- 输入框、按钮、提示文本、主容器使用公共 token

#### MainWindow

- 完全跟随全局主题
- 搜索区、标签栏、热门搜索、历史列表、容器分组改为消费公共 token
- 现有局部 `QSS` 从“写具体颜色”改为“引用主题生成结果”

#### Major dialogs

包括但不限于：

- `AdvancedSettingsDialog`
- `PluginManagerDialog`
- `LiveSourceManagerDialog`
- 其他主要设置/管理弹窗

要求：

- 容器背景、组框、表单、按钮、说明文本跟随全局主题
- 不再各自维护独立配色体系

#### PlayerWindow

采用混合方案：

- 跟随全局主题：
  - 详情面板
  - 侧栏
  - 列表
  - 菜单
  - 设置弹窗
  - 外围按钮和非视频区域
- 保持暗色沉浸：
  - 视频播放区域
  - 底部控制条底板
  - 视频上的悬浮控制层
  - 画面上的遮罩和浮层

这意味着：

- `PlayerWindow` 不应被实现成“一个单独的永久深色窗口”
- 它是“全局主题窗口 + 暗色播放层”的组合

### 8. Refactoring strategy for existing QSS

不建议第一版把所有页面 `QSS` 全量推翻重写。

建议策略：

1. 先建立 `ThemeManager`、token、应用级 palette、应用级全局 `QSS`
2. 再替换最显眼且影响统一性的局部硬编码样式

优先改造区域：

- `MainWindow`
  - 搜索框
  - 顶部操作区
  - 热门/历史内容卡片与按钮
- `AdvancedSettingsDialog`
- `HistoryPage`
- `PosterGridPage`
- `PluginManagerDialog`
- `LiveSourceManagerDialog`
- `PlayerWindow` 外围详情区和控制区

局部页面级 `QSS` 允许保留结构性差异，但不再负责硬编码主题色值。

## Testing

### Storage tests

`tests/test_storage.py`

- 新增 `theme_mode` 默认值测试
- 新增 `theme_mode` round-trip 持久化测试
- 新增非法 `theme_mode` 回退到 `system` 的归一化测试

### Theme manager tests

如新增 `tests/test_theme.py`，至少覆盖：

- `light` / `dark` / `system` 解析逻辑
- 系统主题无法识别时回退到 `light`
- 深色和浅色 token 集差异
- 播放器沉浸层 token 始终偏暗

### App wiring tests

`tests/test_app.py`

- 应用启动时会根据 `theme_mode` 安装主题
- `system` 模式会解析为实际主题后再应用
- 保存主题后会触发重新应用

### UI tests

`tests/test_main_window_ui.py`

- `AdvancedSettingsDialog` 出现 `外观` 页
- 主题选择控件包含 `浅色` / `深色` / `跟随系统`
- 保存后 `AppConfig.theme_mode` 更新

`tests/test_player_window_ui.py`

- `PlayerWindow` 外围区域随全局主题变化
- 播放控制层 / 视频区相关样式保持暗色沉浸表达

必要时可以通过 palette、styleSheet 内容或控件属性来断言主题已切换，而不是只做截图级比较。

## Risks And Mitigations

### Risk 1: Partial migration leaves mixed styles

如果只接入主题底座，但主要页面仍保留大量旧硬编码颜色，用户会看到半主题化状态。

缓解：

- 第一版必须覆盖所有顶层窗口和主要弹窗
- 优先改造最显眼区域，而不是只改一个设置页

### Risk 2: PlayerWindow theme becomes internally inconsistent

如果播放器外围和播放层边界不清，可能会出现一半跟主题、一半随机深色的视觉割裂。

缓解：

- 明确“暗色沉浸层”只作用于视频相关区域
- 详情面板、菜单、设置区全部回归全局主题 token

### Risk 3: Linux platform differences remain visible

不同 Linux 桌面环境对原生 palette、字体、边框的处理不同，可能仍有细微差异。

缓解：

- 采用更强的应用级 palette + QSS 控制，而不是过度依赖平台默认值
- 将平台差异收敛到 `ThemeManager`，不让页面自行补丁化处理

### Risk 4: Future real-time follow-system becomes hard

如果窗口直接依赖配置值而不是依赖统一主题入口，后续加“实时跟随系统变化”会很难。

缓解：

- 本轮所有页面都只能通过 `ThemeManager` 消费解析后的主题
- 不允许在页面里新增平台判断逻辑

## Open Questions Resolved In This Design

- `follow-system` 是否需要实时监听：
  - 不需要，本轮只在应用启动时读取一次
- 主题入口放在哪里：
  - 放在 `AdvancedSettingsDialog`
- 是否覆盖所有顶层窗口和主要弹窗：
  - 是
- 品牌色是否跟系统强调色：
  - 否，固定为应用品牌色
- `PlayerWindow` 是否严格跟随浅/深主题：
  - 否，采用“外围跟随全局主题、播放区保持偏暗”的混合方案
