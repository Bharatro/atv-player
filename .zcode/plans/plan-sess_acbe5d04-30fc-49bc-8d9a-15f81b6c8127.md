# YouTube 播放优化：快速解析与完整 yt-dlp 解析并行 + 低画质自动升级

## 概念映射
- **网页解析（快速解析）**= `YtdlpPlaybackService.resolve_fast()`（`yt-dlp --get-url`）：秒级返回可播的合并流，但格式选择器首选 `best[height<=1080]`，在 YouTube 上几乎总是 360p（itag 18）——这就是"低画质视频"的来源。
- **yt-dlp 解析（完整解析）**= `resolve()/resolve_full()`（`--dump-single-json`）：选取 bestvideo+bestaudio 构建 DASH data-URI 清单（直播为官方 HLS/清单），并带清晰度/字幕/音轨列表。

目标行为：打开播放器时两者**同时启动**；快速结果先起播（快）；完整解析完成后，若当前播放画质低于完整结果画质，自动保进度切换到 DASH/HLS 流。

## 改动

### 1. `src/atv_player/yt_dlp_service.py` — 完整解析竞速注册表
- 把 `resolve()` 缓存检查之后的主体抽为 `_resolve_uncached()`（纯机械重构，公共入口 `resolve()` 保持签名不变：缓存查询 → pending 查询 → `_resolve_uncached()` → 写缓存）。
- 新增 `start_full_resolve_race(url, log=None) -> Future | None`：以 `resolve_full(url, max_height=None, audio_track_id="")`（含字幕）参数起一条 daemon 线程跑 `_resolve_uncached()`，成功后写缓存；用 `concurrent.futures.Future` 承载结果。注册表 `dict[canonical_url → (future, cache_height, audio_id, include_subtitles)]` + `threading.Lock`；已有 pending 或缓存命中时返回 None（不重复跑）。
- `resolve()` 缓存未命中后先查注册表：参数（高度/音轨/字幕）完全匹配的 pending 直接 `future.result()` 复用（hydration 调用与竞速参数天然同键：`h=配置高度, a=auto, subs=all`），异常则回落到自行解析。参数不匹配（如手动切 480p）不受影响。

### 2. `src/atv_player/controllers/youtube_controller.py` — 快速分支同时起跑
- `_resolve_playback_result()` 中 `can_fast_resolve` 分支：先 `service.start_full_resolve_race(source_url)`，再 `resolve_fast()`；若快速解析抛 `ValueError` 则等待竞速 Future 的完整结果直接起播高画质（快速失败不再直接失败）；若竞速已先完成则直接用完整结果。

### 3. `src/atv_player/ui/main_window.py` — 粘贴链接路径同样接入
- `_build_ytdlp_parse_request.load_item()` 的 fast 分支（约 4701 行）加同样的竞速启动与失败兜底，复用服务层能力。

### 4. `src/atv_player/player/mpv_widget.py` — 记录实际视频高度
- `handle_video_out_params` 中保存 params；新增 `current_video_height() -> int | None`（读 `h`）；`load()` 起播时清空，避免上一条目的高度残留。

### 5. `src/atv_player/ui/player_window.py` — hydration 完成后自动升级
- `_PendingPlaybackLoader` 增加快照字段 `playback_started_url` / `playback_started_quality_id`，`_start_playback_loader(hydrate_only=True)` 时记录（回滚材料）。
- `_handle_playback_loader_succeeded` 的 hydrate_only 分支末尾调用新方法 `_maybe_upgrade_ytdlp_playback_quality(item, pending_loader)`：
  - 条件（全部满足）：当前条目仍是 pending 条目、`_is_youtube_resolved_direct_item`、选中画质为 `ytdlp_` 且有高度、`current_video_height()` 非空且**严格小于**目标高度、无进行中的 `_pending_playback_prepare`。直播（不走快速路径）与等高场景自然不触发。
  - 动作：复用 `_change_video_quality_selection` 直连分支的模式——记日志"清晰度提升 360p→1080p"，捕获 `position_seconds()`，`_start_current_item_playback(start_position_seconds=..., pause=not is_playing)`（hydration 时 `apply_result` 已把 `item.url` 写成 DASH/HLS 地址，直接重载即可，跳过 prepare 与现状一致）；同步异常时按快照回滚并尽力恢复原地址播放，日志"清晰度切换失败"。

### 6. 测试
- `tests/test_ytdlp_service.py`（新增或就近文件）：竞速复用不重复跑子进程、参数不匹配不复用、竞速失败回落自行解析。
- `tests/test_youtube_controller.py`：fast 分支启动竞速；`resolve_fast` 失败时采用竞速结果。
- 运行相关 pytest 子集 + 全量回归。

## 效果
- 起播速度不变（快速解析先起播）；完整解析从"起播后 1.5s 才开始"提前到"打开播放器即开始"，总时延约省 2-6 秒。
- 360p 起播后自动切到 1080p DASH（保进度、保暂停状态），画质列表/字幕/音轨同时补全。
- 快速解析失败时直接等完整结果，成功率更高。

## 说明
- 不新增设置项，行为默认开启（升级条件是"目标严格高于当前"，`youtube_max_height` 配置自然封顶）。
- 不涉及 SABR/InnerTube 移植（沿用 2026-08-15 的架构决策）。