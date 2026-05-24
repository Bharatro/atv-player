# 播放窗口剧集标题切换按钮弱化设计

## 背景

播放窗口右侧播放列表顶部有两个模式切换 tab: `剧集标题` 和 `原始文件名`。当前样式使用统一的播放器 tabbar 配置，字重和占用空间都偏强，在播放界面里存在感过高。

本次目标是只降低这两个 tab 的视觉存在感，让它们更像辅助切换控件，而不是主要操作按钮。

## 范围

- 只调整播放窗口 `playlist_title_tabs` 的视觉样式
- 同时缩小字体、内边距、圆角和 tab 间距
- 保留当前两种模式、文案和切换逻辑
- 不修改其他页面或其他 tabbar 的共用样式

## 方案比较

### 方案一: 播放窗口单独覆盖样式

在播放器现有 `build_player_tabbar_qss()` 基础上，为 `playlist_title_tabs` 增加更轻量的专用参数或专用构建函数。

优点:
- 影响范围最小
- 可以精确弱化这两个 tab
- 不会意外改变其他复用播放器 tabbar 的区域

缺点:
- 会增加一处播放器专用样式分支

### 方案二: 直接修改通用播放器 tabbar 样式

统一缩小 `build_player_tabbar_qss()` 的默认值。

优点:
- 实现最直接

缺点:
- 影响所有复用该样式的地方
- 对当前需求来说范围过大

## 选型

采用方案一。播放窗口的这组 tab 有明确的局部语义，适合单独弱化，不应把风险扩散到其他 tabbar。

## 设计细节

### 样式结构

- 保留当前 `theme.py` 中播放器 tabbar 的色彩和状态规则
- 为 `playlist_title_tabs` 提供更紧凑的尺寸参数
- 仅下调尺寸相关属性，不改 hover 和 selected 的状态语义

### 预期调整方向

- `font-size` 下调到比当前更小一级
- `padding` 同步收紧，让 tab 高度和宽度都下降
- `border-radius` 略微减小，避免缩小后仍显得厚重
- `margin-right` 略微减小，减少横向存在感

### 交互与状态

- 默认态更弱
- hover 仍可看出可点击
- selected 仍然清楚标识当前模式

本次不改变:
- tab 顺序
- 默认选中逻辑
- 显隐逻辑
- 播放列表数据映射

## 影响面

- [src/atv_player/ui/player_window.py](/home/harold/workspace/atv-player/src/atv_player/ui/player_window.py:868) 的 `playlist_title_tabs` 样式绑定
- [src/atv_player/ui/theme.py](/home/harold/workspace/atv-player/src/atv_player/ui/theme.py:998) 的播放器 tabbar 样式构建逻辑

## 错误处理

这是纯视觉改动，不引入新的运行时分支。主要风险是选中态对比不足，因此实现时需要保留选中态颜色对比，不做过度淡化。

## 测试

- 手动打开播放窗口，确认 `剧集标题` / `原始文件名` 两个 tab 明显更小
- 验证 hover 和 selected 状态仍可区分
- 验证切换两种模式后播放列表标题显示逻辑不变
- 验证未影响其他播放器侧边栏控件样式
