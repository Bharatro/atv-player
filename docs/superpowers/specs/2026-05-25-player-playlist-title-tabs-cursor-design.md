# 播放窗口标题切换 Tab 手形指针设计

## 背景

播放窗口右侧的标题切换 tab `剧集标题` / `原始文件名` 当前仍使用默认箭头指针。用户希望先把这两个 tab 改成手形指针，强化“这是可点击切换控件”的交互反馈。

用户同时指出，暂时不改播放列表本身；列表项命中手形需要单独评估风险和实现方式。

## 范围

- 只调整播放窗口 `playlist_title_tabs`
- 鼠标移入这两个 tab 区域时显示 `PointingHandCursor`
- 不修改普通播放列表 `QListWidget`
- 不修改 B 站树形播放列表 `QTreeWidget`
- 不改 tab 切换逻辑、文案、显隐和样式

## 方案比较

### 方案一：直接对 `playlist_title_tabs` 设置手形指针

在 `PlayerWindow` 初始化阶段对 `self.playlist_title_tabs` 调用 `setCursor(Qt.CursorShape.PointingHandCursor)`。

优点:
- 改动最小
- 行为明确稳定
- 与播放器里其他按钮的 cursor 设置方式一致

缺点:
- 只覆盖整个 tabbar，不区分是否精确悬停在单个 tab 上

### 方案二：通过事件过滤器按 tab 命中切换 cursor

根据鼠标位置命中具体 tab，再在空白处回退箭头。

优点:
- 交互边界更精细

缺点:
- 对当前需求明显过度设计
- 会引入额外 hover 逻辑，没有必要

## 选型

采用方案一。`playlist_title_tabs` 本身就是一个紧凑的点击区域，直接设置手形指针已经足够表达交互意图，没有必要额外增加命中判断。

## 设计细节

- 在 `src/atv_player/ui/player_window.py` 中，创建 `playlist_title_tabs` 后立即设置手形指针
- 不新增样式表规则
- 不改 `_render_playlist_title_tabs()` 或 `_change_playlist_title_mode()` 的行为

## 风险

这是纯交互提示改动，风险很低。主要确认点只有两项：

- tab 隐藏/显示切换时 cursor 行为保持正常
- 不影响播放器现有视频区域 cursor 管理逻辑

## 测试

- 手动打开播放窗口
- 鼠标移到 `剧集标题` / `原始文件名` tab 上时显示手形
- 鼠标离开 tab 区域后恢复其他区域原有 cursor 行为
- 点击 tab 后标题切换逻辑保持不变
