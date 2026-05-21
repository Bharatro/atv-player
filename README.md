# atv-player

基于 `PySide6` 和 `mpv` 的 `alist-tvbox` 桌面播放器，当前以 Linux 为优先目标平台，同时保留 macOS 和 Windows 打包支持。

应用默认连接 `http://127.0.0.1:4567`，围绕 `alist-tvbox` 后端提供登录、媒体浏览、播放记录、网络直播、插件扩展和独立播放器窗口。

## 文档导航

- [详细帮助文档](docs/help.md)
- [Python Spider 插件开发指南](docs/python-spider-plugin-development-guide.md)

## 核心能力

### 内容入口

- 根据后端能力自动显示豆瓣电影、电报影视、B站、网络直播、Emby、Jellyfin、飞牛影视、盘搜、文件浏览、播放记录等标签页
- 为每个启用的 `TvBox Python` 爬虫插件生成独立标签页，插件过多时自动收入“更多”抽屉并支持搜索
- 顶部全局搜索会并发搜索所有已启用来源，并在标签标题中显示结果数量
- 全局搜索支持直接打开三类地址：
  - `magnet:?` / `ed2k://`：走离线下载流程
  - 常见网盘分享链接：进入网盘详情/解析流程
  - 普通 `HTTP/HTTPS` 链接：走内置全局解析并直接拉起播放器

### 浏览与历史

- 豆瓣电影、电报影视、飞牛影视采用海报网格浏览，支持分类、筛选、分页
- B站、Emby、Jellyfin 支持目录层级导航与播放恢复
- 文件浏览页支持面包屑、排序、分页和按网盘类型筛选
- 播放记录支持分页、删除、清空和双击恢复

### 播放器

- 独立播放器窗口，支持播放/暂停、快进快退、音量、倍速、上一集/下一集、全屏和宽屏模式
- 支持多来源分组、多线路播放列表、自动连播和播放恢复
- 支持主字幕、次字幕、外挂字幕、音轨选择、DASH 清晰度切换
- 支持弹幕搜索、弹幕来源切换、弹幕渲染设置和缓存
- 支持媒体刮削，可手动搜索并补充影片元数据（海报、简介、评分、演员等），也可自动增强
- 详情侧栏可显示海报、元数据、插件自定义动作和播放日志
- 解析型播放项会启用”解析”下拉框，可切换并记住偏好的内置解析器

### 网络直播

- 内置默认远程直播源
- 支持远程 M3U、本地 M3U/`txt`、手动维护三类直播源
- 支持多行 EPG URL 配置与手动立即更新
- 解析 `group-title`、`tvg-logo`、`http-user-agent`、`http-header`
- 会合并同组下同名频道，将多条线路组织成一个播放列表

### 插件

- 支持本地和远程 `TvBox Python` 爬虫插件
- 支持添加、启用/禁用、重命名、编辑配置、刷新、删除、查看日志
- 支持 GitHub 仓库和 `spiders_v2.json` 清单 URL 导入，显示新增/更新/跳过摘要
- 支持上移/下移与排序对话框，排序对话框支持置顶/置底和拖拽移动
- 插件可提供自定义管理动作与播放器详情动作

> 远程插件会执行本地 Python 代码，只应加载受信任来源。

### 本地能力

- 内置本地 HLS 代理（默认 `127.0.0.1:2323`），用于 M3U8 重写、广告片段过滤、TS 分片缓存和 DASH 处理
- 支持远程蓝光 ISO 的 HTTP range 读取、UDF 解析、播放列表检测和流式播放
- 支持 QQ 音乐 `QRC`、酷狗 `KRC`、网易 `YRC` 卡拉 OK 歌词解析与 ASS 渲染

## 环境要求

- Python `3.12+`
- `uv`
- 可用的 `libmpv`
- 一个可访问的 `alist-tvbox` 后端

Linux 上如果系统里没有 `libmpv`，运行和打包都会失败。`build.py` 会在常见系统目录查找它。

如果你需要单独构建较新的 `mpv/libmpv` 运行时，可使用仓库内的辅助脚本：

```bash
scripts/build_mpv.sh
```

常见用法：

```bash
scripts/build_mpv.sh --disable-x86asm
scripts/build_mpv.sh --disable-x86asm --no-install --dry-run
scripts/build_mpv.sh --master
```

说明：

- 默认使用 `mpv-build` 的 release 轨道构建 `mpv/libmpv`
- 默认执行 `sudo ./install`
- 如果缺少 Lua 开发包，脚本会在 `apt-get` 可用时自动执行 `sudo apt-get install -y liblua5.2-dev`
- 如果当前桌面会话是 `X11` 且缺少 `xpresent` 开发包，脚本会自动执行 `sudo apt-get install -y libxpresent-dev`
- 安装完成后建议先执行 `hash -r`，再用 `/usr/local/bin/mpv --version` 和 `ldconfig -p | grep libmpv` 确认新运行时已生效
- 如果遇到 `nasm not found or too old`，可先使用 `--disable-x86asm`
- `--dry-run` 只打印构建命令，便于先检查流程

## 快速开始

安装开发依赖：

```bash
uv sync --group dev
```

启动应用：

```bash
./start.sh
```

`start.sh` 实际执行的是：

```bash
uv run src/atv_player/main.py
```

## 首次使用

1. 启动 `alist-tvbox` 后端。
2. 打开播放器，在登录页输入后端地址、用户名和密码。
3. 登录成功后进入主窗口；应用会记住后端地址、用户名、令牌和上次打开状态，但不会保存密码。
4. 通过顶部标签页或全局搜索进入内容详情，双击或点击播放项拉起独立播放器。
5. 在主窗口或播放器窗口按 `F1` 可以随时打开快捷键帮助。

更完整的界面说明、操作流程、直播源格式示例和排障信息见 [详细帮助文档](docs/help.md)。

## 快捷键速览

### 主窗口

| 快捷键 | 说明 |
|--------|------|
| `F1` | 打开快捷键帮助 |
| `Ctrl+P` | 显示或返回播放器 |
| `Esc` | 显示或返回播放器 |
| `Ctrl+Q` | 退出应用 |

### 播放器窗口

| 快捷键 | 说明 |
|--------|------|
| `F1` | 打开快捷键帮助 |
| `Space` | 播放/暂停 |
| `Enter` | 切换全屏 |
| `W` | 切换宽屏 |
| `D` | 打开弹幕源 |
| `S` | 打开刮削 |
| `Ctrl+D` | 打开弹幕设置 |
| `I` | 显示视频信息 |
| `Ctrl+P` | 返回主窗口 |
| `Esc` | 退出全屏或返回主窗口 |
| `PgUp` | 播放上一集 |
| `PgDn` | 播放下一集 |
| `Left` | 后退 15 秒 |
| `Right` | 前进 15 秒 |
| `Ctrl+Left` | 后退 60 秒 |
| `Ctrl+Right` | 前进 60 秒 |
| `Up` | 音量增加 |
| `Down` | 音量减小 |
| `M` | 静音 |
| `-` | 降低倍速 |
| `+` | 提高倍速 |
| `=` | 恢复 `1.0x` |
| `Ctrl+Q` | 退出应用 |

## 本地数据

应用使用 `Qt` 的标准数据目录和缓存目录。Linux 上通常分别是：

```text
~/.local/share/atv-player
~/.cache/atv-player
```

常见文件和目录：

- 配置数据库：`~/.local/share/atv-player/app.db`
- 插件缓存：`~/.cache/atv-player/plugins`
- 海报缓存：`~/.cache/atv-player/posters`
- 弹幕搜索缓存：`~/.local/share/atv-player/danmaku-search-cache.json`
- 弹幕系列偏好：`~/.local/share/atv-player/danmaku-series-preferences.json`
- 元数据缓存：`~/.cache/atv-player/metadata`
- 元数据手动绑定：`~/.local/share/atv-player/metadata-bindings.json`

应用会持久化以下状态：

- 后端地址、用户名、登录令牌和 `vod token`
- 上次活跃窗口、上次活跃标签页、分类和浏览路径
- 上次播放来源、恢复信息、播放器布局、宽屏模式和日志可见性
- 播放器音量、静音状态、偏好解析器
- 直播源、手动频道、EPG 配置
- 插件配置、缓存路径和加载日志
- 弹幕偏好（启用、行数、显示模式、颜色、位置、速率、字号）
- 元数据增强配置（启用状态、TMDB API Key、Bangumi Token、豆瓣 Cookie、剧集标题增强）
- 元数据手动绑定记录

应用不会保存密码。

## 开发

运行测试：

```bash
uv run pytest
```

运行 `ruff`：

```bash
uv run ruff check .
```

项目采用 `src` 布局，主要目录如下：

- `src/atv_player`：应用代码
- `tests`：单元测试和 UI 测试
- `packaging`：各平台图标和打包资源
- `docs`：用户文档、设计说明与实现计划

## 打包

本地打包和 GitHub Actions 共用同一个入口：

```bash
uv sync --group dev --group package
uv run python build.py current
```

也可以显式指定目标平台：

```bash
uv run python build.py linux
uv run python build.py macos
uv run python build.py windows
```

各平台输出规则：

- Linux：先生成 `PyInstaller` 目录包，再封装成 `AppImage`
- macOS：生成 `.app`
- Windows：生成单文件 `.exe`

Linux 打包额外要求：

- 系统里需要 `appimagetool`
- 系统里需要可用的 `libmpv`

Windows 打包时，`build.py` 会优先从这些位置查找 `mpv` 运行库：

- 环境变量 `ATV_MPV_RUNTIME_DIR`
- 仓库根目录下的 `mpv/`
- 当前 `PATH`

GitHub Actions 会为 Pull Request 和手动触发构建 Linux、macOS、Windows 制品；推送以 `v` 开头的标签时，还会创建 GitHub Release 并上传产物。

## 环境变量

| 变量 | 说明 |
|------|------|
| `ATV_MPV_DEBUG` | 启用 mpv 调试日志输出 |
| `ATV_MPV_RUNTIME_DIR` | Windows 打包时指定 mpv 运行库目录 |
