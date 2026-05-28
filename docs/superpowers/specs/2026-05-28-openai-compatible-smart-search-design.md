# OpenAI-Compatible Smart Search Design

## Summary

为普通用户引入云端 AI 能力：用户在设置页配置一个 OpenAI-compatible API 后，就可以用自然语言搜索影视内容，例如“类似黑镜的高分科幻”“节奏快的悬疑日剧”“适合晚上看的轻松电影”。

第一阶段不要求用户部署本地模型，不引入本地 embedding 依赖，也不把智能搜索绑定到某一家服务商。应用只依赖最常见的 Chat Completions-compatible 接口来解析搜索意图，再用现有的收藏、追剧、历史、TMDB 元数据和插件搜索结果完成检索与排序。

## Goals

- 面向普通用户，避免本地模型、GPU、向量库和命令行部署门槛。
- 支持 OpenAI-compatible API，包括可配置 `base_url`、`api_key` 和 `chat_model`。
- 在全局搜索入口支持自然语言影视搜索。
- 让 LLM 只负责“理解用户意图”，检索结果仍由本地索引、现有元数据和插件搜索提供。
- 建立 AI provider 底座，为后续元数据修正、云端 embedding、字幕翻译预留接口。
- 保护用户体验：无 API 配置或调用失败时，全局搜索仍按现有关键字搜索工作。

## Non-Goals

- 第一阶段不实现本地 LLM、本地 embedding 或向量数据库。
- 第一阶段不实现 Whisper 自动字幕。
- 第一阶段不实现实时双语字幕翻译。
- 第一阶段不实现 AI 自动媒体整理和文件重命名。
- 第一阶段不把所有插件搜索结果长期索引化，只做当前智能搜索所需的最小缓存与排序。
- 第一阶段不引入 OpenAI 专属 Responses API 依赖；兼容服务商支持程度不稳定，后续可作为增强路径。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/app.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/controllers/browse_controller.py` 或新增全局搜索协调器
- 新增 `src/atv_player/ai/` 子模块
- 新增 `src/atv_player/search/` 子模块

主要验证：

- `tests/test_storage.py`
- `tests/test_app.py`
- `tests/test_advanced_settings_dialog.py` 或现有设置弹窗测试
- `tests/test_ai_*.py`
- `tests/test_smart_search_*.py`
- 需要时扩展全局搜索 UI 测试

## Current Problem

当前应用已经具备较强的内容入口和元数据能力：

- 全局搜索可以并发搜索已启用来源。
- 追剧、收藏、历史、TMDB discovery、元数据刮削和多 provider 元数据增强已经存在。
- 插件体系已经能提供大量内容来源。
- SQLite 已用于配置、绑定、收藏、追剧、直播源等持久化。

但对普通用户来说，搜索仍主要依赖明确片名或关键词。用户脑子里的真实需求经常是模糊的：

- “类似黑镜的科幻”
- “晚上随便看点轻松的”
- “节奏快一点的日剧悬疑”
- “评分高但不要太长的电影”

如果直接先做本地 embedding，会出现几个问题：

- 普通用户无法部署模型。
- 打包体积、首次下载、推理速度和跨平台可用性都会变复杂。
- 本地向量索引需要先有稳定的媒体索引和更新策略，否则很容易变成不可解释的黑盒排序。

因此第一阶段应先把云端 AI 接入和结构化意图解析做稳，再逐步增强语义排序。

## Approach Options

### Option A: Local embedding first

先接本地 embedding 模型和向量索引，用向量相似度实现自然语言搜索。

优点：

- 隐私和离线能力更好。
- 后续相似影片推荐和剧情语义搜索上限更高。

缺点：

- 不符合普通用户“无需部署本地模型”的约束。
- 打包和运行依赖明显增加。
- 需要先解决模型下载、缓存、CPU 性能和跨平台兼容。

### Option B: Cloud LLM intent parser first

先让用户配置 OpenAI-compatible API。LLM 把自然语言解析成结构化搜索意图，应用再用本地 FTS、现有元数据和插件搜索结果排序。

优点：

- 用户只需要填 API 配置，不需要部署模型。
- 与第三方 OpenAI-compatible 服务兼容面最大。
- 可解释，容易调试，失败时可回退到普通搜索。
- 能直接复用现有元数据、收藏、追剧、历史和插件搜索能力。

缺点：

- 依赖外部 API。
- 语义召回能力弱于真正 embedding。
- 需要设计好隐私提示和请求最小化。

### Option C: Cloud embedding and chat together

第一阶段同时接入 Chat Completions 和 Embeddings API，直接实现完整语义搜索。

优点：

- 搜索体验更完整。
- 后续推荐系统可以复用向量索引。

缺点：

- API 成本、索引刷新、批量 embedding、错误恢复和数据迁移都需要一起解决。
- 对 MVP 来说风险偏高。
- 第三方 compatible 服务对 embedding 接口的兼容性不如 chat 接口稳定。

## Decision

采用 **Option B: Cloud LLM intent parser first**。

原因：

- 它最符合“普通用户没有本地模型部署能力”的产品约束。
- 它能最快落地一个可用的差异化体验，同时不破坏现有搜索链路。
- 它把 AI 能力放在一个清晰边界内：理解意图，不直接决定最终结果。
- 后续可以在同一 AI provider 配置下继续增加 embedding、元数据修正、字幕翻译等能力。

## Design

### 1. AI configuration

在 `AppConfig` 中新增 AI 配置：

- `ai_enabled: bool = False`
- `ai_base_url: str = ""`
- `ai_api_key: str = ""`
- `ai_chat_model: str = ""`
- `ai_request_timeout_seconds: int = 30`

设置页新增 `AI` 或 `智能` 分组：

- 启用智能功能
- API 地址
- API Key
- Chat 模型
- 超时时间
- “测试连接”按钮

默认行为：

- 默认关闭 AI。
- 未配置时不显示错误，不影响现有搜索。
- API Key 按现有配置保存方式持久化；界面输入框使用密码模式。
- 不内置任何第三方服务商密钥。

### 2. AI client module

新增 `src/atv_player/ai/` 子模块。

推荐文件边界：

- `ai/models.py`
  - `AIProviderConfig`
  - `AIMessage`
  - `AICompletionRequest`
  - `AICompletionResult`
  - `AIError`
- `ai/openai_compatible.py`
  - `OpenAICompatibleClient`
- `ai/search_intent.py`
  - `SmartSearchIntent`
  - `SmartSearchIntentParser`
  - prompt 构造和 JSON 解析

`OpenAICompatibleClient` 只实现第一阶段需要的 chat completion：

- URL 规则：`{base_url}/chat/completions`，同时容忍用户填写带或不带尾部 `/v1`
- Header：`Authorization: Bearer <api_key>`
- Payload：`model`、`messages`、`temperature`、`response_format` 等常规字段
- 超时：使用配置值
- 错误：统一转成用户可读但不泄漏密钥的错误信息

客户端不直接依赖 OpenAI 官方 SDK，优先使用现有 `httpx`，以降低 compatible API 的适配成本。

### 3. Search intent model

LLM 输出严格 JSON，转换为 `SmartSearchIntent`。

字段：

- `query_text`: 原始用户输入
- `mode`: `title_search | smart_discovery`
- `media_types`: `movie | tv | anime | variety` 列表
- `genres`: 风格和类型词，例如 `sci-fi`、`suspense`、`comedy`
- `mood`: `light | dark | tense | relaxing | exciting` 等宽松标签
- `countries`: 国家或地区
- `languages`: 语言
- `year_min`
- `year_max`
- `rating_min`
- `max_runtime_minutes`
- `keywords`: 可用于普通搜索和 FTS 的关键词
- `reference_titles`: “类似黑镜”里的参考作品
- `negative_keywords`: 排除词
- `sort_preference`: `rating | popularity | recent | relevance`

解析策略：

- prompt 要求只输出 JSON。
- JSON 解析失败时回退到普通关键词搜索。
- 字段非法或未知时丢弃，不阻断搜索。
- 保留原始 query，便于日志和回退。

### 4. Smart search coordinator

新增 `src/atv_player/search/` 子模块。

推荐文件边界：

- `search/models.py`
  - `SmartSearchRequest`
  - `SmartSearchCandidate`
  - `SmartSearchResult`
- `search/local_index.py`
  - 第一阶段可先封装现有收藏、追剧、历史、TMDB 绑定数据读取
  - 后续再扩展 SQLite FTS5 表
- `search/ranking.py`
  - 结构化意图评分
- `search/coordinator.py`
  - 调用 intent parser、聚合候选、排序、回退

协调器流程：

1. 收到全局搜索输入。
2. 如果 AI 未启用或配置不完整，走现有搜索。
3. 调用 `SmartSearchIntentParser`。
4. 解析失败时走现有搜索。
5. 从本地数据读取候选：
   - 收藏
   - 追剧
   - 播放历史
   - TMDB discovery/metadata 缓存
   - 手动绑定的 TMDB 元数据
6. 如果本地候选不足，再触发现有插件/全局搜索。
7. 对候选进行评分并返回 UI。

### 5. Ranking

第一阶段采用可解释的加权评分。

主要信号：

- 标题、别名、简介、演员、类型的关键词命中。
- 类型、国家、年份、评分、媒体类型匹配。
- `reference_titles` 命中时，优先使用 TMDB 推荐或同类型/同关键词规则。
- 用户已有行为：
  - 收藏和追剧可提升可信度。
  - 已完整看过的内容在“找新片”语义下可降权。
  - 播放历史可帮助理解口味，但不直接霸榜。

评分结果应保留简单解释文本，例如：

- `科幻 / 悬疑匹配`
- `评分 8.4`
- `来自你的追剧`
- `与参考作品类型相近`

### 6. UI behavior

全局搜索输入框保持一个入口，不新增复杂模式选择。

行为：

- AI 未启用：完全沿用现有搜索。
- AI 启用：输入自然语言时先进入智能搜索流程。
- 搜索状态显示：
  - `理解搜索意图...`
  - `正在搜索本地内容...`
  - `正在补充插件结果...`
- 失败时显示短提示，并自动回退普通搜索。

结果呈现第一阶段尽量复用现有结果列表或卡片，不做大规模 UI 重构。若需要区分来源，增加轻量标签：

- `智能匹配`
- `本地`
- `追剧`
- `收藏`
- `插件`

### 7. Privacy and safety

发送给 AI API 的内容应最小化：

- 第一阶段只发送用户搜索文本和简短 schema，不发送完整媒体库。
- 不发送播放历史、收藏列表、API token、插件配置和本地文件路径。
- 需要利用本地行为数据时，在本地评分阶段完成。

设置页应明确说明：

- 启用后，搜索文本会发送到用户配置的 AI 服务商。
- API Key 只保存在本机配置中。

### 8. Error handling

错误分类：

- 配置缺失：静默回退普通搜索。
- 401/403：提示检查 API Key。
- 404：提示检查 Base URL 或模型名。
- 超时：提示 AI 服务超时并回退。
- JSON 格式错误：记录日志，回退普通搜索。
- 网络错误：提示网络不可用并回退。

日志要求：

- 记录 provider URL host、模型名、错误类型和 request id。
- 不记录 API Key。
- 不记录完整 Authorization header。

### 9. Testing

单元测试：

- `AppConfig` 新字段默认值、迁移、保存和读取。
- `OpenAICompatibleClient` 请求 URL、header、payload、错误转换。
- `SmartSearchIntentParser` 成功解析、非法 JSON 回退、字段归一化。
- `SmartSearchCoordinator` 在 AI 关闭、配置缺失、解析失败、候选不足时的回退。
- `ranking` 对类型、评分、年份、关键词、用户行为的加权。

UI 测试：

- 设置页显示 AI 配置项。
- API Key 输入框不明文显示。
- 测试连接按钮成功/失败状态。
- 全局搜索在 AI 启用时显示智能搜索状态。

集成测试：

- 使用 fake compatible server 或 monkeypatch client 模拟 chat completion。
- 验证“类似黑镜的高分科幻”能解析为包含参考作品、类型和评分约束的 intent。
- 验证 API 失败时仍返回普通搜索结果。

## Future Work

- 云端 Embeddings API：为简介、类型、演员、标题、台词建立向量索引。
- SQLite FTS5 媒体索引：把收藏、追剧、历史、插件缓存和本地媒体统一索引。
- AI 元数据修正：用相同 AI provider 修复标题、年份、季集、版本信息。
- AI 字幕翻译：复用 provider 配置，但需要独立的字幕任务队列和缓存。
- 本地模型高级模式：给高级用户提供可选本地 provider，但不作为普通用户默认路径。
