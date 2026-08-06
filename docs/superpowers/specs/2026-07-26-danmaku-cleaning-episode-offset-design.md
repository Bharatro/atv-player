# 弹幕清洗持久化与剧集级偏移设计

## 目标

将现有基于环境变量的弹幕清洗与时间偏移能力改为应用内可配置、可持久化的功能：

- 全局清洗策略由高级设置编辑，并通过 `AppConfig` 和 `SettingsRepository` 持久化。
- 时间偏移按“系列 + 剧集 + 弹幕来源”持久化。
- 播放器“弹幕源”对话框提供当前剧集的固定秒数偏移控件。
- 偏移只在渲染阶段应用，来源 XML 缓存始终保存不含偏移的基准时间轴。
- 删除所有 `ATV_DANMU_*` 和 `ATV_DANMU_OFFSET` 环境变量入口。

## 非目标

- 不保留按视频时长比例拉伸弹幕时间轴的模式。
- 不让清洗设置保存动作自动重新下载或刷新当前弹幕。
- 不将动态增长的剧集偏移映射写入 `AppConfig` 单行配置。
- 不改变弹幕搜索、三级获取链或候选匹配规则。
- 不重做现有弹幕渲染样式设置对话框。

## 配置模型与存储

`AppConfig` 新增三个全局字段：

```python
danmaku_blocked_words: list[str] = field(default_factory=list)
danmaku_duplicate_window_minutes: int = 0
danmaku_convert_top_bottom_to_scroll: bool = False
```

`app_config` 表新增对应列：

```sql
danmaku_blocked_words TEXT NOT NULL DEFAULT '[]'
danmaku_duplicate_window_minutes INTEGER NOT NULL DEFAULT 0
danmaku_convert_top_bottom_to_scroll INTEGER NOT NULL DEFAULT 0
```

`SettingsRepository` 的首次建表、旧库迁移、`load_config()` 和 `save_config()` 必须同时覆盖这些字段。加载和保存时执行以下规范化：

- 屏蔽词只接受字符串列表；逐项去除首尾空白，丢弃空值并按首次出现顺序去重。
- 重复时间窗转换为整数并限制在 `0..60`；非法值回退为 `0`。
- 顶底转换使用布尔值。

`0` 分钟表示不执行重复内容清洗。三个默认值均保持现有环境变量未设置时的行为。

## 全局清洗

清洗逻辑保留为接收 `DanmakuRecord` 列表和清洗配置的纯函数。`DanmakuService` 通过构造参数接收当前配置加载器，沿用现有 `disabled_provider_ids_loader` 的动态读取模式。每次成功解析 provider 记录后读取最新配置，并按固定顺序调用该函数：

1. 屏蔽包含指定普通文本的记录。
2. 在配置的分钟窗口内对相同内容去重。
3. 将顶部和底部弹幕转换为滚动弹幕。

屏蔽词使用 Unicode `casefold()` 后的普通子串匹配，不解释为正则表达式。配置加载异常时记录日志并返回原记录，不阻断弹幕下载。

通用控制器和插件控制器通过 `DanmakuService` 获得清洗后的 XML。直解析控制器绕过 `DanmakuService`，因此它必须接收同一配置加载器，将直解析 payload 转换成 `DanmakuRecord` 后调用同一个纯清洗函数，再通过 `build_xml()` 生成基准 XML。这样所有新获取路径共享同一清洗语义，同时不会对缓存命中结果重复处理。

删除 `DanmakuService` 对以下环境变量的全部读取：

- `ATV_DANMU_BLOCKED_WORDS`
- `ATV_DANMU_GROUP_MINUTE`
- `ATV_DANMU_CONVERT_TOP_BOTTOM`
- `ATV_DANMU_OFFSET`

同时删除仅服务于环境变量规则的 `OffsetRule`、`parse_offset_rules()`、`resolve_offset_seconds()` 和百分比偏移分支。固定秒数的 `apply_time_offset()` 保留给渲染链路。

## 剧集与来源偏移模型

`PlayItem` 新增当前播放期运行时字段：

```python
danmaku_offset_seconds: float = 0.0
```

`DanmakuSeriesPreference` 新增向后兼容字段：

```python
episode_source_offsets: dict[str, dict[str, float]] = field(default_factory=dict)
```

JSON 结构为：

```json
{
  "jianlai": {
    "provider": "tencent",
    "page_url": "https://v.qq.com/example",
    "title": "剑来 第12集",
    "search_title": "剑来",
    "episode_source_offsets": {
      "episode:12": {
        "tencent": -3.0,
        "bilibili": 1.5
      }
    },
    "updated_at": 1785032000
  }
}
```

剧集键按以下优先级生成：

1. 播放列表可推断出正整数集号时使用 `episode:<number>`。
2. 存在弹幕搜索集数时，规范化空白和大小写后使用 `label:<value>`。
3. 存在稳定的 `vod_id` 或媒体 URL 时，对其生成稳定摘要并使用 `item:<digest>`。
4. 电影或其他单项内容使用 `single`。

来源键使用当前选中 `DanmakuSourceOption.provider`。没有系列键、剧集键或来源键时，偏移回退为 `0` 且控件禁用。

`DanmakuSeriesPreferenceStore` 提供按系列、剧集和来源读取、保存偏移的 API。保存 `0` 时删除对应来源记录；剧集映射变空后删除剧集键。旧 JSON 缺少 `episode_source_offsets` 时按空映射读取。非法嵌套结构、非有限数值和超出 `-600..600` 的记录逐项忽略，不影响同文件中的其他偏好。

应用创建一个共享的 `DanmakuSeriesPreferenceStore` 实例，并注入插件、通用弹幕和直解析弹幕控制器。存储内部使用可重入锁串行化读改写，并通过同目录临时文件加 `Path.replace()` 原子落盘，避免后台来源偏好保存与 UI 偏移保存互相覆盖。三个控制器向播放器暴露兼容的读取与保存方法。测试替身或旧控制器没有这些方法时，播放器按偏移 `0` 继续工作。

## 缓存与渲染边界

弹幕来源解析和清洗完成后生成基准 XML。该 XML 不应用剧集偏移，并以不含偏移的形式写入来源缓存。

播放器生成 ASS 时将 `PlayItem.danmaku_offset_seconds` 传入字幕转换链路。字幕解析为记录后调用固定秒数 `apply_time_offset()`，再生成 ASS 事件。偏移值必须成为 ASS 缓存键的一部分，确保同一 XML 的不同偏移不会复用错误文件。

弹幕 XML 缓存键增加版本盐。升级后不再读取旧版本缓存，因为旧缓存可能已经由 `ATV_DANMU_OFFSET` 永久改写时间轴。升级后的首次播放会重新获取并写入新的基准 XML 缓存。

任何加载路径，包括自动搜索、手动切换来源、预取命中和缓存恢复，在渲染前都必须为当前 `PlayItem` 同步对应的剧集/来源偏移。重复加载只能从基准 XML 重新计算，不能在已偏移 XML 上叠加。

## 高级设置 UI

高级设置现有元数据页增加“弹幕清洗”分组，放在弹幕来源分组之后，包含：

- 屏蔽词多行文本框，每行保存为一个普通文本规则。
- 重复内容时间窗 `QSpinBox`，范围 `0..60`，后缀为“分钟”。
- “顶底弹幕转为滚动弹幕”复选框。

打开对话框时从 `AppConfig` 填充控件。点击保存时规范化屏蔽词列表、写回三个字段并调用现有 `save_config` 回调。保存成功不触发网络请求，也不修改当前已经加载的弹幕；之后重新获取或切换来源时使用新配置。

## 弹幕源对话框 UI

在现有 provider/候选双栏列表下方、状态与操作按钮上方增加独立校准栏：

- 标签“当前剧集偏移”。
- `QDoubleSpinBox`，范围 `-600.0..600.0`，单步 `0.5`，一位小数，后缀“秒”。
- “归零”按钮。

打开对话框、切换剧集或完成来源切换后，阻断控件信号并填入当前系列、剧集和来源的已保存偏移。没有已加载弹幕、没有选中来源或后台来源任务进行中时禁用校准栏。

用户调整数值后启动单次 `250ms` 定时器。定时器触发时：

1. 更新当前 `PlayItem.danmaku_offset_seconds`。
2. 通过控制器保存当前系列、剧集和来源的偏移。
3. 从基准 XML 重新生成并挂载 ASS。
4. 刷新对话框动作状态。

“归零”将数值设为 `0.0`，经过同一保存和重渲染路径。偏移保存失败时保留当前运行时渲染效果并写入播放器日志，但不能显示已持久化成功的状态。渲染失败沿用现有弹幕加载失败处理，不损坏已保存的来源偏好或基准 XML。

## 数据流

全局清洗：

```text
高级设置
  -> AppConfig
  -> SettingsRepository / app_config
  -> DanmakuService / 直解析控制器动态读取
  -> records 共享纯函数清洗
  -> 不含偏移的基准 XML 与来源缓存
```

剧集偏移：

```text
弹幕源对话框
  <-> PlayItem.danmaku_offset_seconds
  <-> DanmakuSeriesPreferenceStore[series][episode][provider]
  -> 基准 XML + offset
  -> ASS 缓存与播放器字幕轨道
```

## 测试策略

实施遵循测试先行，至少覆盖：

1. `AppConfig` 三个字段的默认值。
2. 新数据库和旧数据库迁移后的列、默认值、保存/加载往返。
3. 屏蔽词列表与重复时间窗的非法值规范化。
4. 普通文本屏蔽、窗口去重、顶底转换及固定处理顺序。
5. 通用、插件和直解析新获取路径使用相同清洗策略，缓存命中不重复清洗。
6. 设置所有旧环境变量后仍不改变处理结果。
7. 旧系列偏好 JSON 兼容读取。
8. 同一剧集不同 provider、同一系列不同剧集的偏移隔离。
9. 偏移归零删除、损坏数据容错、范围限制、并发保存和原子写入。
10. 新 XML 缓存版本不命中旧缓存。
11. ASS 缓存键区分不同偏移，重复渲染不叠加。
12. 高级设置控件初值、保存回写和不触发当前弹幕刷新。
13. 弹幕源对话框控件布局、启用状态、`250ms` 合并、归零和即时重挂载。
14. 切剧集、切来源、缓存恢复时加载正确偏移。
15. 缺少新偏移 API 的控制器测试替身继续按偏移 `0` 工作。

聚焦测试通过后运行完整测试套件。每个文件写入后从磁盘重读；每个提交后执行 `git log -1 --oneline` 和 `git show --stat --oneline HEAD`，确认提交与文件真实存在。

## 验收标准

- 重启应用后，全局清洗设置保持不变。
- 重新获取弹幕后，新的清洗设置生效；当前已加载弹幕不会因保存设置自动刷新。
- 同一剧集切换弹幕来源时，各来源恢复自己的偏移。
- 切换剧集并返回后，恢复该剧集与来源的偏移。
- 调整偏移后无需重新下载弹幕即可看到时间轴变化。
- 归零恢复基准 XML 时间轴，重复操作不会叠加偏移。
- 环境变量不再影响清洗或偏移。
- 旧偏好与旧数据库可升级加载；旧偏移污染风险通过 XML 缓存版本隔离消除。
