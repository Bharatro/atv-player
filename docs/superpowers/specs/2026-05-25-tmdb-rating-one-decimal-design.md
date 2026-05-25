# TMDB评分一位小数写入设计

## 概要

本次调整只修改 `TMDB` 来源评分的写入规范，不改其他来源评分的格式规则。

目标：

- `TMDB` 的 `vote_average` 在写入 `MetadataRecord.rating` 时统一规范为 1 位小数。
- 所有后续复用 `MetadataRecord.rating` 的追更、详情和列表链路自动获得一致结果。
- 非 `TMDB` 来源评分保持现状，不引入跨来源格式化副作用。

## 变更范围

涉及模块：

- `src/atv_player/metadata/providers/tmdb.py`
- `tests/test_metadata_tmdb_provider.py`
- 可能补充一条使用方回归测试，确认下游拿到规范化后的值

不涉及模块：

- 非 `TMDB` metadata provider
- UI 展示层单独格式化逻辑
- 数据库存储结构
- 已有历史数据迁移

## 现状问题

当前 `TMDBProvider` 直接把 `vote_average` 原样转成字符串写入 `MetadataRecord.rating`。

这会导致：

- 整数评分可能写成 `8`
- 多位小数评分可能写成 `7.64`
- 下游虽然复用了同一个字段，但结果依赖上游原始返回值，不够稳定

问题根因在于 `TMDB` provider 写入时没有做来源内格式规范化。

## 方案对比

### 方案一：在 TMDB provider 写入时规范化

做法：

- 在 `src/atv_player/metadata/providers/tmdb.py` 增加一个很小的评分规范化函数
- `get_detail()` 和 `get_detail_full()` 写入 `MetadataRecord.rating` 时统一调用

优点：

- 只影响 `TMDB`
- 所有下游自动一致
- 变更点最少，语义最清晰

缺点：

- 旧数据需要重新抓取后才会变成新格式

### 方案二：在元数据合并层按 provider 条件格式化

优点：

- 能在写入业务对象前做统一兜底

缺点：

- 规则离数据源更远
- 容易遗漏其他 `TMDB` 写入入口
- 会把 provider 特有规则塞进通用层

### 方案三：只在展示层格式化

优点：

- 不改数据

缺点：

- 不符合本次“写入时规范化”的要求
- 各页面容易出现不一致

推荐采用方案一。

## 设计

### 写入规则

新增一个仅供 `TMDBProvider` 使用的评分规范化函数。

规则：

- 空值返回空字符串
- 非数字值返回空字符串
- 数字值统一按四舍五入保留 1 位小数
- 输出始终是字符串，例如：
  - `8` -> `8.0`
  - `7.64` -> `7.6`
  - `7.66` -> `7.7`

### 落点

规范化逻辑放在 `src/atv_player/metadata/providers/tmdb.py`。

调用点：

- `TMDBProvider.get_detail()`
- `TMDBProvider.get_detail_full()`

原因：

- 这两个方法是 `TMDB` 详情写入 `MetadataRecord.rating` 的直接入口
- 在这里处理可以让追更、详情、搜索补全后的详情刷新都自动复用一致结果

### 数据流

`TMDB API vote_average` -> `TMDBProvider` 评分规范化 -> `MetadataRecord.rating` -> 后续落库/合并/展示

## 错误处理

- 不因评分格式异常抛出异常
- 对 `None`、空字符串、无法解析为数字的值返回空字符串
- 不对其他字段做联动修正

## 测试策略

先写失败测试，再实现代码。

覆盖点：

- `get_detail()` 返回的 `TMDB` 评分会规范成 1 位小数
- `get_detail_full()` 返回的 `TMDB` 评分会规范成 1 位小数
- 整数评分会带上 `.0`
- 非法评分值会安全退回空字符串
- 至少一条下游链路测试确认追更或元数据使用方拿到的是规范化后的 `rating`

## 风险与兼容性

风险较小，主要是：

- 某些现有测试如果断言 `TMDB` 原始评分字符串，需要同步更新为一位小数格式

兼容策略：

- 规则限定在 `TMDBProvider`
- 不改 `MetadataRecord` 结构
- 不碰非 `TMDB` provider，避免横向回归

## 非目标

本次不处理：

- 历史数据库中已保存的 `TMDB` 评分批量迁移
- 非 `TMDB` 来源评分统一格式化
- UI 层再次格式化评分
- 评分字段改为数值类型
