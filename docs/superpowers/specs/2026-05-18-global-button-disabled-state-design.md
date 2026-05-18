# Global Button Disabled State Design

## Summary

当前应用里的按钮禁用态不统一，也不够明显。

已确认的问题有两类：

- 一部分按钮禁用后只是轻微变灰，仍然像“还能点”
- 不同按钮体系各自定义禁用态，普通按钮、圆形图标按钮、胶囊按钮的视觉语言不一致

这轮只统一全局按钮禁用态的视觉表达，不改任何业务启用/禁用逻辑，不新增新的按钮类型。

## Goals

- 让按钮禁用态在浅色 / 深色主题下都一眼可辨
- 保留禁用按钮的轮廓和标签可读性，不把控件直接“抹掉”
- 统一普通按钮、圆形图标按钮、胶囊按钮三类按钮的禁用态语言
- 收敛散落在页面里的局部 `QPushButton:disabled` 样式，优先回到主题 helper

## Non-Goals

- 不改任何按钮的启用/禁用条件
- 不改按钮文案、布局、尺寸或交互流程
- 不重做 hover / pressed 的整体视觉体系
- 不扩展到 `QComboBox`、`QSpinBox`、`QLineEdit` 等非按钮控件

## Scope

主要改动：

- `src/atv_player/ui/theme.py`
- `src/atv_player/ui/main_window.py`
- 需要时补充少量使用通用按钮 helper 的页面

主要验证：

- `tests/test_theme.py`
- `tests/test_main_window_ui.py`
- 需要时补充使用胶囊按钮页面的样式断言

## Current Problem

当前主题系统已经统一了按钮的默认态、hover 态和部分强调态，但 disabled 仍然存在三个问题：

### 1. 默认按钮的禁用态过轻

应用级 `QPushButton` 主要依赖全局样式表。当前 disabled 视觉没有形成足够的层次差，容易和默认态混在一起。

### 2. 圆形图标按钮没有显式 disabled 方案

圆形图标按钮通过 `build_round_icon_button_qss(...)` 生成样式，但 helper 只定义了默认态和 hover 态。禁用后会退回 Qt 默认表现或继承不完整状态，和应用其他按钮不一致。

### 3. 胶囊按钮与局部文本按钮各自为政

胶囊按钮通过 `build_pill_button_qss(...)` 生成样式，局部历史/操作按钮又在 `main_window.py` 里手写 `QPushButton:disabled`。它们的禁用态对比度和边框策略都不同，导致同一页面里“不可用”的视觉信号不一致。

## Approach Options

### Option A: 低饱和 + 降对比

保持当前按钮轮廓，只统一降低 disabled 的背景、边框、文字对比度。

Pros:

- 风险最低，和现有主题延续性最好
- 不需要引入新的边框语言或额外装饰
- 适合同时覆盖三类按钮

Cons:

- 需要精确控制颜色层级，否则仍可能不够明显

### Option B: 低饱和 + 虚线边框

在降对比基础上，为 disabled 按钮增加虚线边框，强化“不可操作”。

Pros:

- 识别速度最快

Cons:

- 视觉提示偏强，容易比当前整体界面更“跳”
- 对圆角图标按钮和胶囊按钮会显得过于设计化

### Option C: 低饱和 + 内凹质感

在降对比基础上，通过轻微内阴影制造“压下去”的禁用感。

Pros:

- 比纯灰化更清晰
- 比虚线更克制

Cons:

- Qt 样式下质感控制更脆弱
- 额外质感会增加不同平台上的不确定性

## Decision

采用 **Option A**。

这次需求的核心不是创造一个新的禁用态符号，而是让现有主题体系下的 disabled 明确、稳定、统一。继续保留按钮轮廓，再通过背景、边框、文字统一降对比，是最稳妥也最容易全局落地的方案。

## Design

### 1. Unified Disabled Token Semantics

在 `ThemeTokens` 中补充按钮禁用态所需的语义颜色，而不是在每个 helper 里直接写死 disabled 颜色。

方向：

- `button_disabled_bg`
- `button_disabled_border`
- `button_disabled_text`

这些 token 需要在浅色 / 深色主题下都满足两个要求：

- 和 enabled 态有明确区分
- 仍保留文字和轮廓可读性

按钮禁用态不依赖 `opacity` 作为主表达，避免控件整体发虚或图标一起被过度冲淡。

### 2. Default QPushButton Disabled State

更新应用级全局 `QPushButton` disabled 样式：

- 背景从正常按钮底色过渡到更平、更低对比的表面
- 边框切换到比默认态更弱但仍可见的描边
- 文字切换到统一的 disabled 文本色
- hover / pressed 在 disabled 下不再提供互动反馈

目标是让普通按钮看起来“存在但不可用”，而不是“像加载失败的按钮”或“像仍可点击但颜色浅了一点”。

### 3. Round Icon Button Disabled State

为 `build_round_icon_button_qss(...)` 增加显式 disabled 规则。

要求：

- 圆形轮廓保留
- 图标颜色和边框一起进入 disabled 语义
- 背景对比度下降，但不能和页面底色完全糊在一起

这样 `MainWindow` 里的搜索图标按钮在禁用时会和文本按钮呈现同一套状态语言，而不是单独像一个“没加载图标”的控件。

### 4. Pill Button Disabled State

为 `build_pill_button_qss(...)` 增加 disabled 规则，并确保它与 `checked` 状态不冲突。

要求：

- disabled 优先级高于 hover
- disabled 时不再保留可点击筛选按钮的活跃感
- 即使按钮是圆角胶囊，也保持与默认按钮一致的灰化策略

这会直接覆盖筛选按钮、继续播放等使用胶囊 helper 的场景。

### 5. Local Handwritten Disabled Rules

检查并收敛局部手写 disabled 样式，尤其是 `main_window.py` 中的 `_action_button_qss()`。

设计要求不是把所有局部按钮都强行改成同一个外观，而是让它们至少遵守同一 disabled 语义：

- 局部文本按钮仍可保持轻量、透明背景
- 但 disabled 文本色必须与全局 token 对齐
- 如果局部按钮没有边框和底色，就至少保证颜色层级与全局一致

换句话说，局部风格可以保留，disabled 信号不能各自解释。

### 6. Boundaries

这轮不处理以下内容：

- `PlayerWindow` 沉浸式控制按钮的独立层级设计
- 下拉框、输入框、滑块等其他控件的 disabled 视觉
- 任何按钮的启用/禁用业务条件

如果后续需要把播放器按钮的 disabled 进一步做成沉浸式专属方案，那会是另一轮独立样式任务。

## Testing Strategy

### Theme Tests

更新 `tests/test_theme.py`，验证：

- 全局 `QPushButton` QSS 含 disabled 规则
- `build_round_icon_button_qss(...)` 含 disabled 规则
- `build_pill_button_qss(...)` 含 disabled 规则
- disabled 使用 token 语义，而不是依赖透明度作为主实现

这些测试以 QSS 输出结构断言为主，不做截图测试。

### UI Tests

更新 `tests/test_main_window_ui.py` 或相关页面测试，验证：

- 全局搜索图标按钮继续使用统一 helper，并具备 disabled 样式路径
- 局部文本操作按钮 disabled 颜色与当前 token 对齐

如有必要，可为使用胶囊按钮的页面增加一条样式断言，避免 helper 更新后某一类按钮漏掉 disabled 规则。

## Risks And Mitigations

- Risk: disabled 对比度仍然不够。
  - Mitigation: 用独立 token 明确管理背景、边框、文字三层，而不是只改文字色。

- Risk: 局部轻量按钮被改得过重。
  - Mitigation: 保留局部透明背景风格，只统一 disabled 语义颜色。

- Risk: 胶囊按钮的 `checked` 和 `disabled` 选择器互相覆盖。
  - Mitigation: 在 helper 中显式定义状态优先级，确保 disabled 最终落地稳定。

## Implementation Order

1. 在 `theme.py` 中补充 disabled button token。
2. 更新全局 `QPushButton`、圆形图标按钮、胶囊按钮 helper 的 disabled 规则。
3. 收敛 `main_window.py` 中手写的局部 disabled 颜色。
4. 补充和更新对应测试断言。
