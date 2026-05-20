# Main Window Navigation Tab Contrast Design

## Goal

修复 Windows 深色主题下主窗口顶部导航 tab 标题对比度不足的问题，同时保持 Linux 和浅色主题下的现有交互与布局稳定。

## Scope

- 只处理主窗口顶部导航 tab 和其相邻的“更多”按钮。
- 不修改播放器侧栏 tab、弹窗 tab 或全局 `QTabBar` 默认样式。

## Approach

- 在 `src/atv_player/ui/theme.py` 中新增主窗口导航专用样式构建函数，显式定义 `QTabBar::tab` 的默认、hover、selected 颜色和背景，避免 Windows 原生深色绘制接管文本颜色。
- 在 `src/atv_player/ui/main_window.py` 中集中应用导航 tab 和“更多”按钮样式，并在主题刷新路径中重复调用，保证运行时切换主题也会同步更新。
- 用 `tests/test_main_window_ui.py` 增加回归测试，断言深色主题下导航 tab 的样式字符串包含显式文字色和选中态配色。

## Constraints

- 不扩大为全局 `QTabBar` 样式，避免影响播放器和其他对话框。
- 不调整导航 tab 的数量、顺序、溢出逻辑或尺寸计算方式。
- 不依赖 `QPalette` 单独修复，因为 Windows 下原生 tab 文本绘制不稳定。

## Testing

- 运行主窗口 UI 测试，验证深色主题导航 tab 样式已显式设置。
- 运行共享主题测试，验证新增样式构建函数输出稳定。
