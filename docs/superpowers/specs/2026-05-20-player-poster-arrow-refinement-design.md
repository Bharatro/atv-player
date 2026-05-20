# Player Poster Arrow Refinement Design

## Summary

调整播放器详情区海报切换箭头的布局与视觉样式：

- 不再使用 `previous.svg` / `next.svg`
- 改用 Qt 内置小箭头图标
- 将左右按钮放到海报左右两侧，与海报处于同一行
- 弱化按钮视觉权重，避免抢海报主体

本轮只调整详情区海报导航的展示方式，不改变海报切换的数据来源、循环逻辑或 metadata 相关状态管理。

## Goals

- 让左右箭头紧贴海报两侧，而不是单独占一整行。
- 去掉自定义 svg 图标，改用系统/Qt 内置小箭头。
- 降低按钮的视觉存在感，让海报继续作为主要视觉焦点。
- 保持当前多海报切换、单海报隐藏、首尾循环等行为不变。

## Non-Goals

- 不调整海报尺寸。
- 不改动海报切换的索引逻辑。
- 不新增 hover 动画、透明渐变遮罩或覆盖式按钮。
- 不修改视频 overlay、音频封面、原始/增强 metadata 的业务逻辑。

## Current Problem

当前实现里：

- 海报 `poster_label` 单独位于一行
- 左右按钮放在海报下方的独立导航行
- 按钮使用 `previous.svg` / `next.svg`

这带来两个问题：

- 导航按钮和海报的视觉关联不够直接，用户需要在海报下方再找一次控制
- svg 按钮的强调度偏高，容易从海报本体上夺走注意力

## Approach Options

### Option A: Overlay arrows on top of poster

做法：

- 将左右箭头覆盖在海报左右边缘上，垂直居中

优点：

- 视觉上最接近图片轮播组件

缺点：

- 会遮挡海报边缘
- 需要额外处理层级和点击区域
- 与当前 Qt 布局结构不如外侧布局稳定

### Option B: Place arrows outside poster on the same row

做法：

- 用一行布局承载 `左箭头 + 海报 + 右箭头`
- 按钮位于海报外侧

优点：

- 不遮挡海报
- 点击区域稳定
- 改动最小，适配当前 `poster_label` 结构自然

缺点：

- 比覆盖式方案多占一点横向空间

### Option C: Keep current row separation and only weaken button styling

做法：

- 保持按钮在海报下方
- 只换成内置箭头并弱化样式

优点：

- 布局改动最少

缺点：

- 仍然不满足“放在海报两边”

## Decision

采用 **Option B**。

原因：

- 这是最直接满足“放在海报两边”的方案。
- 不遮挡海报内容，交互区域更清晰。
- 能在不引入复杂 overlay 逻辑的前提下，把导航和海报组合成一个完整单元。

## Design

### 1. Layout

将当前：

- `poster_label`
- 独立的 `_poster_navigation_widget`

改成一个统一行布局，结构为：

- 左箭头按钮
- `poster_label`
- 右箭头按钮

布局要求：

- 海报保持居中主位
- 两个按钮贴近海报左右两侧
- 外侧保留少量弹性空间，避免过分贴边

### 2. Button widget choice

按钮改用 `QToolButton`，不再复用 `_create_icon_button(...)` 的 svg 按钮路径。

按钮属性：

- `setArrowType(Qt.LeftArrow / Qt.RightArrow)`
- 小尺寸
- 指针手型
- 仅在存在多海报时显示

理由：

- Qt 内置箭头比文本箭头更稳定
- 不依赖额外资源文件
- 比当前 svg 方案更轻量

### 3. Visual styling

按钮视觉弱化要求：

- 无明显边框
- 低对比度前景
- 默认背景透明
- hover 态只做轻微背景提示，不做强强调
- 不使用 primary/secondary 控制按钮的视觉语言

期望效果：

- 箭头是“可发现但不突出”的辅助控件
- 海报仍然是这一块区域的视觉中心

### 4. Behavior

以下行为保持不变：

- 多海报时显示按钮
- 单海报或无海报时隐藏按钮
- 点击左右按钮切换详情区海报
- 首尾循环切换
- metadata hydration、scrape apply、原始/增强切换时重置到第一张

### 5. Testing

更新现有 player window 海报导航测试，覆盖：

- 按钮依然正确显示/隐藏
- 按钮与海报处于同一行，且分别位于海报左右两侧
- 点击切换和首尾循环行为不变

不需要为视觉弱化写像素级断言；只需验证控件类型、布局关系和核心交互不回退。
