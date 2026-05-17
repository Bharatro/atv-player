# Network Proxy Settings Design

## Summary

为桌面播放器新增“高级设置 > 网络代理”能力，覆盖应用内主要外部网络请求，并把 `yt-dlp` 一并纳入代理控制。

第一版目标：

- 高级设置对话框改为标签页结构，至少分为 `元数据` 和 `网络代理`
- 支持互斥代理模式：`直连` / `系统代理` / `HTTP` / `HTTPS` / `SOCKS5`
- 手动代理支持带认证的完整 URL，例如 `http://user:pass@host:port`
- 支持用户可编辑的直连规则
- 将代理策略统一接入 `ApiClient`、元数据抓取、弹幕、解析源、海报、插件下载、HLS 代理上游请求和 `yt-dlp`

本轮重点不是做完整“代理中心”，而是先建立稳定的数据模型、代理决策层和跨模块接线方式，为后续“按域名分流”预留演进空间。

## Goals

- 用户可以在应用内统一配置网络代理，而不是依赖外部环境变量。
- 第一版代理配置能覆盖用户实际最依赖的外网链路，尤其是 `YouTube`、`TikTok`、`Instagram` 和各类解析/弹幕请求。
- 本地 API、局域网资源和其他需要直连的地址可以通过规则显式绕过代理。
- 不把代理判断逻辑散落在各个业务模块里。
- 为后续“按域名分流”保留清晰的扩展位，而不推翻第一版结构。

## Non-Goals

- 本轮不实现按域名分流或多代理路由。
- 本轮不实现“代理配置列表”“多个代理方案切换”“优先级规则编辑器”。
- 本轮不新增“按模块单独开关代理”的 UI。
- 本轮不做代理可用性测试、出口 IP 检测或诊断面板。
- 本轮不改造成完整统一网络会话工厂。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/app.py`
- `src/atv_player/api.py`
- 新增网络代理决策模块，例如 `src/atv_player/network_proxy.py`
- 逐步接入主要网络调用点：
  - `src/atv_player/ui/poster_loader.py`
  - `src/atv_player/playback_parsers.py`
  - `src/atv_player/danmaku/*`
  - `src/atv_player/metadata/providers/*`
  - `src/atv_player/plugins/loader.py`
  - `src/atv_player/proxy/*`
  - `src/atv_player/yt_dlp_service.py`

主要验证：

- `tests/test_storage.py`
- 新增代理决策/规则测试
- `tests/test_api_client.py`
- `tests/test_main_window_ui.py`
- 新增高级设置对话框测试
- `tests/test_yt_dlp_service.py`
- 按需补充解析源/海报/弹幕相关测试

## Current Problem

当前项目里的外部网络访问没有统一代理入口：

- 高级设置目前只有元数据增强相关项，没有任何网络代理配置。
- 网络请求分散在 `ApiClient`、元数据 provider、弹幕 provider、海报加载、解析器、插件下载、HLS 代理和 `yt-dlp` 子进程中。
- 如果只追加 UI 而不建立统一代理决策层，后续会出现“部分请求走代理、部分不走”的不一致行为。
- `yt-dlp` 是用户最依赖代理的链路之一，但它使用子进程调用，不会自动复用应用内 `httpx` 配置。

## Approach Options

### Option A: Scatter proxy params into each call site

做法：

- 在各个 `httpx.get/post`、provider 和 `yt-dlp` 调用点分别读取当前配置并拼接代理参数。

优点：

- 早期代码改动表面上最直接。

缺点：

- 判断逻辑会复制到大量模块里。
- 后续加系统代理、直连规则、按域名分流时会迅速失控。
- 很难保证 `httpx`、`requests` 和 `yt-dlp` 的行为一致。

### Option B: Add a centralized proxy decision layer and thin adapters

做法：

- 新增统一的代理配置模型和代理决策层。
- 业务模块只向代理层询问“这个 URL 应该直连还是走哪个代理”。
- 再用薄适配层分别对接 `httpx`、`requests` 兼容调用和 `yt-dlp`。

优点：

- 第一版复杂度可控，但不会堵死后续演进路径。
- 代理规则、模式判断和协议转换集中管理，行为更一致。
- `yt-dlp` 这种特殊出口也能复用同一套决策语义。

缺点：

- 需要引入一个新模块和一组配套测试。

### Option C: Build a full network session factory now

做法：

- 立即把所有网络请求都重构到统一网络工厂/会话层，再由工厂负责代理、超时和重试等横切逻辑。

优点：

- 长期结构最干净。

缺点：

- 对当前需求明显过重。
- 改动面过大，回归风险不适合第一版代理功能。

## Decision

采用 **Option B**。

原因：

- 当前最缺的是“统一代理语义”，不是“完整网络基础设施重构”。
- Option B 可以覆盖本轮最重要的用户场景，同时把规则判断收拢到一个位置。
- 这样第一版就能把 `httpx`、`requests` 兼容调用和 `yt-dlp` 三类出口纳入同一套配置，而不把项目拖进大规模重构。

## Design

### 1. AppConfig and persistence

在 `AppConfig` 中新增：

- `network_proxy_mode: str = "direct"`
- `network_proxy_url: str = ""`
- `network_proxy_bypass_rules: list[str] = field(default_factory=list)`

约束：

- `network_proxy_mode` 仅允许：
  - `direct`
  - `system`
  - `http`
  - `https`
  - `socks5`
- `network_proxy_url` 保存完整代理 URL，手动模式时要求包含协议头
- `network_proxy_bypass_rules` 为用户输入后的规范化规则列表，按行存储

`SettingsRepository` 同步：

- 初始化建表时新增对应列
- 老库迁移时补列
- `load_config()` / `save_config()` 支持完整 round-trip

存储建议：

- `network_proxy_mode`：`TEXT`
- `network_proxy_url`：`TEXT`
- `network_proxy_bypass_rules`：`TEXT`，以 JSON 数组持久化

默认值：

- 模式默认为 `direct`
- 代理 URL 默认为空
- 直连规则默认为内置建议值，但用户可编辑保存：
  - `localhost`
  - `127.0.0.1`
  - `::1`
  - `10.0.0.0/8`
  - `172.16.0.0/12`
  - `192.168.0.0/16`
  - `.local`

### 2. Advanced settings dialog

现有 `AdvancedSettingsDialog` 调整为标签页结构：

- `元数据`
- `网络代理`

`网络代理` 页字段：

- `代理模式`
  - 互斥单选或等价互斥控件
  - 选项：`直连` / `系统代理` / `HTTP` / `HTTPS` / `SOCKS5`
  - 语义：用户在三种手动代理类型中选择其一，所选代理对全部 `http/https` 目标请求生效，而不是“按目标协议分别填写不同代理”
- `手动代理地址`
  - 单行输入框
  - 支持 `user:pass`
  - 示例提示：
    - `http://127.0.0.1:7890`
    - `socks5://user:pass@127.0.0.1:1080`
- `直连规则`
  - 多行文本框
  - 一行一条
- `覆盖范围说明`
  - 只读文案，明确第一版会影响：
    - API
    - 元数据
    - 解析源
    - 弹幕
    - 海报
    - 插件下载
    - HLS 代理上游请求
    - `yt-dlp`

行为：

- 选择 `直连` 或 `系统代理` 时，手动代理输入框禁用但保留值。
- 选择手动模式时，要求代理地址非空且协议与模式一致。
- 保存前逐行校验直连规则；非法规则直接提示具体行号，不静默忽略。
- 点击保存时回写 `AppConfig` 并调用现有 `save_config`。
- 点击取消时不落盘。

本轮不做：

- 测试连接按钮
- 自动检测系统代理内容并展示详情
- 代理连通性日志面板

### 3. Proxy model, rules, and decision layer

新增统一代理模块，例如 `src/atv_player/network_proxy.py`。

建议拆为三个小单元：

#### `ProxyConfig`

承载规范化后的配置：

- `mode`
- `proxy_url`
- `bypass_rules`

#### `ProxyBypassRule`

封装单条直连规则及匹配逻辑。第一版支持四类语义：

- 精确主机：`localhost`、`api.example.com`
- 域名后缀：`.local`、`.example.com`
- 单个 IP：`127.0.0.1`
- CIDR 网段：`10.0.0.0/8`

匹配规则：

- 只基于目标 URL 的 `host`
- 不匹配路径、查询参数、端口
- 域名大小写不敏感
- IP/CIDR 使用标准库 `ipaddress` 解析

#### `ProxyDecider`

输入目标 URL，输出统一决策结果：

- `direct`
- `system`
- `manual(proxy_url)`

判定顺序：

1. 目标 URL 不是 `http` 或 `https`：直连
2. 目标主机命中直连规则：直连
3. 模式是 `direct`：直连
4. 模式是 `system`：系统代理
5. 模式是手动代理：返回配置的代理 URL

设计约束：

- `ProxyDecider` 只负责决策，不直接发请求
- 业务代码不自行解析直连规则
- 后续“按域名分流”时，在 `ProxyDecider` 基础上扩展，不重写 UI 和存储结构

### 4. Adapters for different network clients

由于项目中同时存在 `httpx`、`requests` 风格调用和 `yt-dlp` 子进程，代理层需要提供薄适配方法。

建议能力：

- 为 `httpx` 生成合适的请求/客户端参数
- 为 `requests` 兼容调用生成 `proxies`
- 为 `yt-dlp` 生成 `--proxy`

约束：

- `system` 模式不在应用内重复解析系统代理；直接让底层客户端使用环境默认行为
- 手动代理模式下统一把代理 URL 透传给目标客户端
- 对于命中直连规则的 URL，适配层必须显式产生“禁用代理”的效果，而不是依赖隐式默认值

### 5. Integration points

第一版统一覆盖下列调用路径：

#### `ApiClient`

- 所有到上游服务的 `httpx.Client` 请求都纳入代理决策
- 本地 `127.0.0.1` API 默认通过直连规则绕过代理，但用户可编辑规则

#### Metadata providers

- `TMDBClient`
- `BangumiClient`
- 本地豆瓣抓取客户端
- 其他直接使用 `httpx.get/post` 的 provider

#### Danmaku providers and direct parse

- `bilibili`
- `iqiyi`
- `mgtv`
- `tencent`
- `youku`
- `direct_parse`

#### Poster loading and playback helpers

- 海报下载
- 解析源网络请求
- 远程蓝光/播放预处理中的外部请求

#### Plugin and proxy infrastructure

- 远程插件下载
- HLS 代理拉取上游 m3u8、分片和密钥资源

#### `yt-dlp`

- 解析 `YouTube`、`TikTok`、`Instagram` 等来源时，命令行显式携带代理参数
- 若目标 URL 命中直连规则，则该次 `yt-dlp` 调用不传手动代理

### 6. Validation and error handling

保存配置时的校验：

- `direct` / `system`：允许代理地址为空
- 手动 `http` / `https` / `socks5`：代理地址必填
- 手动模式下，代理 URL 协议必须与模式一致
  - `http` 模式要求 `http://`
  - `https` 模式要求 `https://`
  - `socks5` 模式要求 `socks5://`
- 直连规则逐行解析，任何非法行都中止保存并提示：
  - 行号
  - 原始内容
  - 基本错误原因

运行时错误策略：

- 不在第一版引入“代理失败自动回退直连”
- 请求失败仍按现有业务错误链路上抛
- 保存时尽可能前置拦截格式问题，减少运行时歧义

### 7. Future extension path

第一版设计必须为“按域名分流”保留扩展位：

- UI 已有独立 `网络代理` 标签页
- 数据模型已独立出代理配置字段
- 决策逻辑集中在 `ProxyDecider`

后续做域名分流时，可以新增：

- 规则列表：`pattern -> mode/proxy`
- 更细粒度的匹配优先级
- 多代理方案

这些扩展不应要求重写当前第一版的存储结构和主接线方式。

## Testing Strategy

至少覆盖以下层级：

### Storage

- 新字段默认值
- 老库迁移补列
- `network_proxy_bypass_rules` JSON round-trip

### Rule parsing and matching

- 精确主机命中
- 域名后缀命中
- 单个 IP 命中
- CIDR 命中
- 非法规则报错

### Decision layer

- `direct` 模式始终直连
- `system` 模式在未命中直连规则时返回系统代理
- 手动代理模式在未命中直连规则时返回代理 URL
- 非 `http/https` URL 直连

### Adapters

- `httpx` 适配输出
- `requests` 适配输出
- `yt-dlp` `--proxy` 参数生成

### UI

- 标签页展示
- 模式切换导致输入框启用状态变化
- 非法代理 URL 阻止保存
- 非法直连规则阻止保存

### Key integration points

- `ApiClient` 请求能够读取代理决策
- `yt-dlp` 调用能按配置追加/省略代理参数
- 关键外部请求入口至少选择一两个代表性模块补回归测试

## Risks

- 项目内部分请求使用的是一次性 `httpx.get/post`，部分是 `httpx.Client`，接线方式不统一，容易漏接。
- `yt-dlp` 的代理参数是进程级行为，和应用内请求并不是一套机制，必须单独测试。
- 用户可编辑直连规则后，默认本地直连保护不再是“硬编码安全网”，文案需要足够明确。
- 第一版如果对“系统代理”语义处理过重，反而会与各平台环境变量行为打架，因此应保持薄适配。
