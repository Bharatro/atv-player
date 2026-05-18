# Custom Window Title Bar Design

## Summary

为 `atv-player` 的所有应用内自建窗口和对话框引入统一的自定义标题栏，并接入现有主题系统，解决当前不同窗口混用系统标题栏、视觉层级不统一、窗口控制行为分散的问题。

本轮目标是建立一套可复用的无边框窗口底座，让主窗口、登录页、播放器和主要自建对话框都共享一致的标题栏样式、窗口控制逻辑和主题刷新路径。

用户已确认的边界：

- 应用内所有自建窗口/对话框都应使用自定义标题栏
- `QFileDialog`、`QColorDialog`、`QInputDialog` 等系统或 Qt 原生弹窗允许继续保留原生标题栏
- `PlayerWindow` 在全屏时隐藏自定义标题栏，退出全屏后恢复

## Goals

- 为所有应用内自建顶层窗口和对话框提供统一的自定义标题栏视觉和交互。
- 让标题栏样式接入现有 `ThemeManager` / token 体系，而不是各窗口各自硬编码。
- 统一窗口拖拽、双击最大化/还原、最小化、关闭等基础行为。
- 为后续新增窗口提供稳定的复用底座，避免继续复制粘贴窗口 chrome 代码。
- 保持 `PlayerWindow` 的沉浸式播放体验，全屏时不显示标题栏。

## Non-Goals

- 本轮不替换 `QFileDialog`、`QColorDialog`、`QInputDialog`、`QMessageBox`、`QProgressDialog` 等标准/原生弹窗。
- 本轮不实现真正的系统级窗口 resize hit-test 或平台原生阴影模拟。
- 本轮不重做页面内部布局，只改窗口 chrome 和承载结构。
- 本轮不引入 macOS traffic-light 风格的跨平台仿真按钮，统一采用当前应用主题语言。
- 本轮不处理运行中系统主题变化监听，沿用现有主题刷新机制。

## Scope

主要改动：

- `src/atv_player/ui/theme.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/ui/login_window.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/ui/plugin_manager_dialog.py`
- `src/atv_player/ui/plugin_reorder_dialog.py`
- `src/atv_player/ui/live_source_manager_dialog.py`
- `src/atv_player/ui/manual_live_source_dialog.py`
- `src/atv_player/ui/help_dialog.py`
- `src/atv_player/ui/window_chrome.py`

主要验证：

- `tests/test_main_window_ui.py`
- `tests/test_login_window_ui.py`
- `tests/test_player_window_ui.py`
- `tests/test_plugin_manager_dialog.py`
- `tests/test_plugin_reorder_dialog.py`
- `tests/test_live_source_manager_dialog.py`
- 需要时新增 `tests/test_window_chrome.py`

## Current Problem

当前工程里的窗口 chrome 存在几个直接问题：

- 主窗口、登录页、播放器、自建对话框都在使用各自默认的系统标题栏，外观和应用主题割裂。
- 已有主题系统主要覆盖内容区控件，标题栏仍然完全由平台默认实现，导致视觉统一性中断。
- `PlayerWindow`、`LoginWindow`、`MainWindow`、多个 `QDialog` 的窗口行为由各自类隐式承担，没有统一复用层。
- 一些对话框是动态创建的裸 `QDialog`，如果继续沿用当前模式，后续很容易遗漏主题化或行为一致性。

在当前代码中，主要受影响的窗口类型有三类：

- 顶层主界面窗口：`MainWindow`、`LoginWindow`、`PlayerWindow`
- 独立类定义的自建对话框：`AdvancedSettingsDialog`、`PluginManagerDialog`、`PluginReorderDialog`、`LiveSourceManagerDialog`、`ManualLiveSourceDialog`、`ShortcutHelpDialog`
- 运行时创建的局部 `QDialog`：播放器中的“弹幕设置”“刮削”“弹幕源”“插件日志”等

如果只做零散样式补丁，而不建立统一底座，后续每新增一个窗口都还会重复处理：

- 无边框 flag
- 标题栏布局
- 拖拽行为
- 最大化/还原按钮
- 主题刷新
- 内容容器包裹

## Approach Options

### Option A: Base-class architecture

做法：

- 新增可复用的标题栏组件
- 新增 `ThemedMainWindowBase` / `ThemedWidgetWindowBase` / `ThemedDialogBase`
- 由各窗口和对话框继承统一底座，内容区挂载到底座提供的容器中

优点：

- 结构最清晰
- 行为最集中
- 后续新增窗口时复用成本最低
- 更适合覆盖运行时动态创建的自建对话框

缺点：

- 需要调整若干现有类的继承和布局挂载方式

### Option B: Composition wrapper

做法：

- 保持现有窗口类不变
- 提供 `CustomTitleBar` 和内容包裹壳层，把已有根布局再包一层

优点：

- 局部改动较小

缺点：

- `QMainWindow`、普通 `QWidget` 顶层窗口、`QDialog` 三套类型适配会变复杂
- 运行时动态创建的对话框更容易出现不一致
- 长期维护性较差

### Option C: Per-window patching

做法：

- 每个窗口各自设置 `FramelessWindowHint`
- 各自插入标题栏和拖拽逻辑

优点：

- 初期改动看起来最直接

缺点：

- 重复代码最多
- 漏改和行为漂移风险最高
- 与“统一窗口底座”的目标相违背

## Decision

采用 **Option A**。

原因：

- 这次需求覆盖的是“所有应用内自建窗口和对话框”，不是单点改造。
- 当前工程同时存在 `QMainWindow`、顶层 `QWidget`、静态 `QDialog`、动态 `QDialog`，只有基类方案能稳定收敛这些差异。
- 标题栏、拖拽、最大化、主题刷新、本体内容挂载都属于窗口 chrome 级职责，集中到统一底座更符合长期演进方向。

## Design

### 1. Unified window chrome layer

新增一个统一窗口 chrome 模块，提供一个共享标题栏组件和三类基础窗口壳：

- `CustomTitleBar`
- `ThemedMainWindowBase`
- `ThemedWidgetWindowBase`
- `ThemedDialogBase`

职责分工：

- `CustomTitleBar`
  - 负责标题文本、窗口控制按钮、拖拽区域、双击行为
- `ThemedMainWindowBase`
  - 面向 `QMainWindow`
  - 负责无边框窗口 flag、chrome 根布局、标题栏、central content 承载、最大化状态样式
- `ThemedWidgetWindowBase`
  - 面向顶层 `QWidget`
  - 负责无边框窗口 flag、根布局、圆角/边框容器、内容区承载、最大化状态样式
- `ThemedDialogBase`
  - 负责无边框对话框 flag、根布局、内容区承载、`accept/reject` 语义不变

这里不再让各个窗口自己拼标题栏。

### 2. Title bar behavior

统一标题栏提供以下行为：

- 显示窗口标题文本，并跟随 `setWindowTitle()` 结果同步
- 提供关闭按钮
- 对普通窗口提供最小化按钮
- 对允许最大化的窗口提供最大化/还原按钮
- 标题栏空白区支持拖拽移动窗口
- 双击标题栏时切换最大化/还原

对话框的默认行为：

- 显示标题
- 提供关闭按钮
- 默认不显示最大化按钮
- 不要求提供最小化按钮

这样可以避免对话框和主窗口出现相同的控制密度。

### 3. Window container model

所有接入自定义标题栏的窗口都采用统一承载结构：

- 最外层窗口：负责实际顶层生命周期和 window flags
- chrome 根容器：负责边框、圆角、背景和主题对象名
- 顶部标题栏
- 内容区容器：由业务窗口把现有主体布局挂进去

这意味着：

- `MainWindow` 需要把现有 central content 改为挂载到新的内容容器
- `LoginWindow` 和 `PlayerWindow` 需要把当前根布局迁移到基类内容容器
- `QDialog` 子类需要把当前 `QVBoxLayout(self)` 改为挂到基类提供的内容容器

### 4. Theme integration

标题栏不单独走局部硬编码样式，而是接入现有主题 token 系统。

`theme.py` 需要补充的语义方向包括：

- `titlebar_bg`
- `titlebar_border`
- `titlebar_text`
- `titlebar_subtle_text`
- `titlebar_button_bg`
- `titlebar_button_hover_bg`
- `titlebar_button_pressed_bg`
- `titlebar_button_close_hover_bg`
- `titlebar_button_close_pressed_bg`
- `window_chrome_bg`
- `window_chrome_border`

样式规则：

- 普通页面窗口使用当前浅/深主题的窗口级 token
- 标题栏按钮视觉应与当前应用按钮风格一致，而不是平台默认矩形系统按钮
- 最大化时可移除外层圆角，恢复时重新显示圆角

### 5. MainWindow integration

`MainWindow` 当前继承 `QMainWindow`，这是本轮结构上最敏感的一类。

目标行为：

- 主窗口改为使用统一自定义标题栏
- 保留现有头部操作区、搜索区、导航区、插件抽屉和页面切换逻辑
- 不改变业务控件层级关系，只改变外层承载方式

实现方向：

- `MainWindow` 继承 `ThemedMainWindowBase`
- 原有主内容区域整体作为内容容器的子树挂载
- 最大化状态下根容器取消圆角和外边距，避免出现系统最大化后四周留白

### 6. LoginWindow integration

`LoginWindow` 当前是简单顶层 `QWidget`，最适合作为基类接入样板。

目标行为：

- 使用统一标题栏和主题色边框
- 保持原有居中表单布局和异步登录逻辑
- 不引入额外播放器类视觉元素

实现方向：

- `LoginWindow` 继承 `ThemedWidgetWindowBase`
- 原有表单布局整体挂入基类内容容器

这是最简单的普通窗口改造对象，也适合作为标题栏基础行为的首个覆盖点。

### 7. PlayerWindow integration

`PlayerWindow` 需要特殊处理，因为它既是顶层窗口，又存在全屏沉浸场景。

目标行为：

- 普通窗口模式下显示自定义标题栏
- 全屏模式下隐藏标题栏
- 退出全屏时恢复标题栏
- 不破坏现有控制层、视频区、宽屏/全屏逻辑

约束：

- 标题栏只属于窗口模式，不属于全屏沉浸层
- 全屏切换时需要同时同步标题栏显隐和相关布局边距
- 标题栏的主题应与播放器外围 UI 协调，但不能干扰视频区沉浸层

实现方向：

- `PlayerWindow` 继承 `ThemedWidgetWindowBase`
- 当前根布局整体挂入基类内容容器
- 进入全屏时只隐藏标题栏和相关外边距，不重写现有播放区内容结构

### 8. Dialog coverage

本轮覆盖的自建对话框分为两类：

- 独立类定义的对话框
- 运行时创建的局部 `QDialog`

独立类定义的对话框全部改为继承 `ThemedDialogBase`：

- `AdvancedSettingsDialog`
- `PluginManagerDialog`
- `PluginReorderDialog`
- `LiveSourceManagerDialog`
- `ManualLiveSourceDialog`
- `_ManualEntryFormDialog`
- `ShortcutHelpDialog`

运行时创建的局部 `QDialog` 需要收敛成统一构造入口，避免遗漏：

- 播放器中的弹幕设置
- 刮削对话框
- 弹幕源对话框
- 插件日志对话框

核心原则：

- 只要是应用自己构造的对话框，就应通过统一自定义标题栏底座创建
- 标准/原生对话框继续保持原生标题栏

### 9. Standard dialog boundary

以下类型明确不进入本轮自定义标题栏覆盖范围：

- `QFileDialog`
- `QColorDialog`
- `QInputDialog`
- `QMessageBox`
- `QProgressDialog`

原因：

- 这些类型本身依赖平台或 Qt 标准行为
- 强行包壳会增加兼容风险，且不符合用户已确认的边界
- 其中一部分还承担文件系统/系统色板/输入法等原生交互职责

因此，本轮要求的是：

- 应用自建窗口和对话框统一风格
- 标准系统弹窗保持稳定可用

### 10. Testing

测试重点不是像素级视觉断言，而是结构和行为一致性断言。

至少覆盖以下方面：

- `MainWindow`、`LoginWindow`、`PlayerWindow` 存在自定义标题栏对象
- 主要自建对话框存在自定义标题栏对象
- 运行时创建的播放器对话框首次打开时也带自定义标题栏
- `PlayerWindow` 进入全屏时标题栏隐藏，退出全屏后恢复
- 主窗口最大化状态下窗口 chrome 状态正确切换
- 原生 `QFileDialog` / `QColorDialog` 入口调用路径不受影响

对于测试实现，优先断言：

- 特定 `objectName`
- 基类类型
- 标题栏可见性
- 标题栏按钮存在性
- 全屏切换前后的可见状态

## Risks

- `QMainWindow` 改造成统一窗口基类时，若 central content 挂载方式处理不当，可能破坏现有布局初始化顺序。
- `PlayerWindow` 的全屏逻辑和现有沉浸式控制层耦合较深，需要避免标题栏显隐影响视频区尺寸和事件处理。
- 运行时动态创建的裸 `QDialog` 如果没有统一构造入口，后续仍可能遗漏自定义标题栏。
- UI 测试如果直接依赖窗口类型或旧布局根对象，改造后需要同步更新断言。

## Rollout Order

推荐实现顺序：

1. 建立 `CustomTitleBar` 与基础无边框窗口/对话框底座
2. 先接入 `LoginWindow` 和一个简单对话框，验证基础行为
3. 接入 `MainWindow`
4. 接入 `PlayerWindow` 并补全全屏标题栏显隐逻辑
5. 接入其余自建对话框
6. 收敛播放器内动态创建的局部 `QDialog`
7. 完成 UI 测试补强

这样可以先稳定基础组件，再处理最复杂的播放器和主窗口。
