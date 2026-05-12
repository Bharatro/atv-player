# Startup Plugin Async Loading Design

## Summary

当前应用启动时会在 `AppCoordinator._show_main()` 里同步调用插件管理器的 `load_enabled_plugins()`。当插件数量较多、插件初始化较慢或网络依赖阻塞时，主窗口会长时间不显示，用户会误以为程序卡死。

本次改动目标是让主窗口优先显示，再在后台异步加载插件。加载期间主窗口保持可用，插件区域显示明确的“插件加载中”占位状态；加载完成后再把真实插件 tab 插入到现有导航结构里。失败时不阻塞主流程，而是给出可见错误和手动重试入口。

## Goals

- 主窗口优先显示，不再等待插件同步加载完成。
- 插件加载期间，插件区域有明确、稳定的占位状态。
- 插件加载完成后平滑替换为真实插件 tab。
- 插件加载失败时主窗口仍可正常使用。
- 不破坏现有插件 tab 溢出、`更多` 抽屉、延迟加载页面、插件管理回刷等行为。

## Non-Goals

- 不改造插件管理器内部的插件加载实现。
- 不引入全局 splash screen 或阻塞式启动对话框。
- 不在本次范围内支持启动阶段的插件加载取消。
- 不改变插件加载顺序、启用逻辑、版本逻辑或导入逻辑。

## Current Flow

当前流程位于 [app.py](/home/harold/workspace/atv-player/src/atv_player/app.py:252)：

1. `_show_main()` 创建 API client 和 controller。
2. 同步调用 `self._plugin_manager.load_enabled_plugins(...)`。
3. 得到 `spider_plugins` 后才创建 `MainWindow`。
4. 因此插件初始化耗时会直接阻塞首屏显示。

## Proposed Flow

### Startup

`AppCoordinator._show_main()` 改为：

1. 先创建 `MainWindow`，传入空的 `spider_plugins=[]`。
2. 立即返回主窗口并显示。
3. 由主窗口在显示后启动后台插件加载任务。
4. 后台任务完成后，将结果回写到主线程，更新插件 tab。

这样主窗口出现时间只受基础 controller 和窗口构造影响，不再被插件加载链路阻塞。

### Main Window Loading State

主窗口新增一套轻量插件启动状态：

- `idle`: 已有真实插件，正常状态。
- `loading`: 启动阶段后台加载中。
- `failed`: 启动阶段加载失败。

在 `loading` 状态下：

- 顶部插件区域显示一个固定占位 tab，文案为 `插件加载中`。
- 这个占位 tab 不参与真实插件页逻辑，不会触发插件 controller 加载。
- 固定 tab、`文件浏览`、`播放记录` 仍正常可用。

在 `failed` 状态下：

- 占位 tab 文案切为 `插件加载失败`。
- 主窗口可见位置显示一条简短错误状态。
- 提供一个“重试加载插件”的入口。

在加载成功后：

- 占位 tab 消失。
- 用真实插件定义替换当前插件区域。
- 继续沿用现有插件溢出分配和 `更多` 抽屉逻辑。

## Architecture

### AppCoordinator Responsibility

`AppCoordinator` 仍然负责构建加载插件所需的依赖，例如：

- `drive_detail_loader`
- `offline_download_detail_loader`
- `plugin_manager`

但它不再同步拿到 `spider_plugins` 结果后才创建主窗口，而是把“如何加载插件”的任务入口交给主窗口或通过回调传给主窗口。

推荐做法：

- 在 `MainWindow` 构造参数中新增一个可调用对象，例如 `plugin_loader_task`。
- 这个对象由 `AppCoordinator` 封装，内部调用现有 `load_enabled_plugins(...)` 兼容分支。
- `MainWindow` 只关心“触发后台加载”和“接收加载结果”，不复制插件管理器的兼容调用细节。

这样插件加载策略仍由应用协调层持有，UI 层只处理状态和结果。

### MainWindow Responsibility

`MainWindow` 新增：

- 启动阶段插件加载状态字段
- 占位插件 tab 定义
- 后台线程启动方法
- 加载成功/失败回调
- 重试入口
- 关闭窗口后的结果忽略保护

`MainWindow` 保持现有 `_rebuild_spider_plugin_tabs()` 为真实插件 UI 构建入口；异步结果到达后，只是更新 `_plugin_definitions` 并调用这条既有路径。

## Data Flow

### Success Path

1. `AppCoordinator` 创建 `MainWindow(spider_plugins=[], plugin_loader_task=...)`
2. `MainWindow` 初始渲染固定 tab + 占位 tab + trailing tab
3. `MainWindow.showEvent()` 或初始化后的单次启动逻辑触发后台线程
4. 后台线程执行 `plugin_loader_task()`
5. 成功后通过 Qt signal 回到主线程
6. `MainWindow` 写入 `_plugin_definitions`
7. 调用 `_rebuild_spider_plugin_tabs()`
8. 清除占位 tab 和加载状态

### Failure Path

1. 后台线程执行 `plugin_loader_task()` 抛异常
2. 通过 Qt signal 回到主线程
3. `MainWindow` 切换为 `failed` 状态
4. 占位 tab 改为失败状态，显示错误提示和重试入口

### Close Safety

如果主窗口关闭时后台插件加载尚未完成：

- 不等待线程结束
- 线程完成后若窗口已失效，则忽略结果
- 不再刷新 UI、不写入已销毁控件

这与现有主窗口异步请求的 guard 思路保持一致。

## UI Behavior

### Placeholder Tab

占位 tab 放在插件 tab 区域，也就是固定 tab 与 `文件浏览/播放记录` 之间。这样用户能直接感知“插件区域正在准备”，同时不会干扰固定内容导航。

占位文案：

- 加载中：`插件加载中`
- 失败：`插件加载失败`

### Retry Entry

失败重试入口建议放在主窗口 header 区域，优先选一个轻量 `QPushButton`，只在失败状态显示。原因：

- 不需要把失败 tab 做成复杂交互容器
- 可见性高
- 不影响现有 tab 容器的简单语义

### Navigation Consistency

加载完成前：

- 不显示真实插件 tab
- 不显示插件 `更多` 按钮

加载完成后：

- 统一进入现有插件 tab 分配逻辑
- 如果插件很多，继续只显示一部分，剩余进入 `更多`

## Error Handling

- 插件加载失败不影响主窗口其他功能。
- 错误信息应简短展示，不弹阻塞式 `QMessageBox`。
- 同一启动周期内只保留最近一次插件加载结果。
- 重试期间如果已经在加载，重复点击应被忽略。

## Testing

需要覆盖：

- 主窗口不等待插件同步加载即可显示。
- 插件未加载完成时显示 `插件加载中` 占位 tab。
- 异步成功后占位 tab 被真实插件 tab 替换。
- 异步失败后显示失败状态和重试入口。
- 关闭窗口后迟到的插件加载结果不会写回 UI。
- 插件加载完成后仍保持现有 tab 溢出和 `更多` 行为。

## Risks

- 如果把插件加载兼容分支逻辑从 `AppCoordinator` 复制到 `MainWindow`，会造成职责扩散。
- 如果占位状态直接混入真实插件定义列表但没有明确区分，可能污染现有插件页构建逻辑。
- 如果线程完成回调没有做窗口存活保护，会引入关闭窗口后的 UI 访问异常。

## Recommendation

采用“主窗口先显示 + 后台异步加载插件 + 插件区占位 tab”的方案。

这是首屏体验最好的方案，同时对现有结构的侵入也相对可控：

- 插件管理器实现无需大改
- `MainWindow` 只新增一层启动状态管理
- 真实插件 UI 仍复用现有 `_rebuild_spider_plugin_tabs()` 路径
