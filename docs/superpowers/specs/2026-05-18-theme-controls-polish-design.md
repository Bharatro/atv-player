# Theme Controls Polish Design

## Summary

在现有主题系统基础上，补一轮控件视觉打磨，重点解决两个已确认问题：

- 下拉框仍然像原生默认控件，和品牌主题脱节
- `PlayerWindow` 底部播放控制按钮层级不清，部分图标在深色控制区里可见性不足

这轮只做样式层和图标呈现层增强，不改主题模式逻辑，不改播放器交互逻辑。

## Goals

- 让 `QComboBox` 在浅色 / 深色主题下都具备统一品牌感，而不是平台默认观感
- 强化 `PlayerWindow` 控制区的状态反馈，明确区分主播放键和次级控制键
- 解决深色控制区里黑色图标不清晰的问题
- 保持当前“全局主题 + 播放区沉浸深色”的混合方案

## Non-Goals

- 不新增新的主题模式或品牌色方案
- 不替换整套图标资源文件
- 不改播放器布局结构、按钮数量或快捷键逻辑
- 不做运行中跟随系统主题变化

## Scope

主要改动：

- `src/atv_player/ui/theme.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/ui/player_window.py`
- 需要时补充 `src/atv_player/ui/icon_cache.py` 或一个新的主题图标 helper

主要验证：

- `tests/test_theme.py`
- `tests/test_main_window_ui.py`
- `tests/test_player_window_ui.py`

## Design

### 1. Branded combobox styling

在 `theme.py` 中新增统一的 `QComboBox` 样式 helper，覆盖：

- 闭合态背景、边框、圆角、文字色
- `hover` / `focus` / `disabled` 状态
- 下拉箭头区域的独立视觉分区
- 弹出列表的背景、hover、选中态

风格方向：

- 维持现有米色 / 深色底与橙色品牌色体系
- 比当前 `QLineEdit` 和普通按钮更强调“可展开控件”的边界
- focus 时使用品牌色边框，不再依赖平台默认高亮

### 2. Player control hierarchy

播放器控制区分为两级：

- 一级：`play_button`
  - 更大点击面积
  - 实心品牌色背景
  - 更强 hover / pressed 反馈
- 二级：上一集、下一集、前进、后退、静音、宽屏、全屏、弹幕、详情等按钮
  - 深色底板上更亮的描边和背景层次
  - hover 时明显提亮
  - pressed 时进一步收紧/加深反馈

目标是让用户第一眼能识别“播放主键”，并能在深色播放区里快速分辨其它控制键。

### 3. Runtime icon tinting

不逐个替换黑色图标资源，而是在运行时对单色图标做着色。

规则：

- 主播放键图标使用高对比浅色前景
- 次级按钮图标使用沉浸层前景色
- hover / active 状态允许跟随按钮状态切换到更亮的品牌相关前景

这样可以同时解决：

- 深色背景上的黑色图标不可见
- 同一图标在浅色 / 深色 / 沉浸层中重复维护多份资源的问题

### 4. Theme token extension

为样式 helper 补充少量语义 token，避免把这轮样式写死在组件里。

新增或细化的 token 方向：

- `input_hover_border`
- `input_focus_ring`
- `menu_bg`
- `menu_hover_bg`
- `menu_selected_bg`
- `player_button_bg`
- `player_button_hover_bg`
- `player_button_pressed_bg`
- `player_button_border`
- `player_button_icon`
- `player_primary_button_bg`
- `player_primary_button_hover_bg`
- `player_primary_button_pressed_bg`
- `player_primary_button_icon`

### 5. Refresh behavior

这轮新增的样式必须接入现有 `_apply_theme()` 刷新链路，确保：

- 切换主题并保存后，设置弹窗中的下拉框立即更新
- `PlayerWindow` 已打开时，底部控制区按钮和图标随主题刷新

## Testing

- 为 `QComboBox` 样式 helper 增加 token 断言
- 为 `AdvancedSettingsDialog` 中的主题下拉框增加样式断言
- 为 `PlayerWindow` 增加：
  - 主播放键样式断言
  - 次级控制键样式断言
  - 图标在深色沉浸控制区下使用浅色前景的断言

## Decision

采用“强调品牌色和状态反馈”的方案：

- 主播放键做强强调
- 次级键做清晰但次一层的操作反馈
- 图标统一运行时着色，而不是替换资源
