# Cache Management In Advanced Settings Design

## Goal

Add cache management to Advanced Settings so users can inspect cache usage by category, open cache directories, clear individual categories, and clear all application cache.

## Scope

- Add a new `缓存管理` tab to `AdvancedSettingsDialog`.
- Show total cache size and total file count.
- Show per-category cache size and file count.
- Support opening the root cache directory and each category directory.
- Support clearing each category independently and clearing all cache.
- Support deleting cache files older than a user-selected number of days.
- Keep application data, settings, login state, playback history, and data under `app_data_dir()` untouched.

## Categories

The cache manager scans the app cache root returned by `app_cache_dir()`.

- `插件缓存`: `plugins`
- `海报缓存`: `posters`
- `元数据缓存`: `metadata`
- `弹幕缓存`: `danmaku`
- `播放缓存`: `playlists`, `subtitles`
- `其他缓存`: files and directories directly under the cache root that are not covered by the categories above

## File System Behavior

Statistics count regular files recursively and sum their byte sizes. Directories are not counted as files.

Clearing a category removes contents from that category's configured paths but keeps the root/category directories available for later use. Clearing all removes contents directly under the application cache root and recreates the root directory.

Age-based cleanup deletes regular files whose last modified time is older than the selected cutoff. It then removes empty directories below the affected cache paths while keeping the cache root and category root directories. The first UI version applies age-based cleanup to all cache categories.

Errors from stat, delete, or open actions are surfaced to the UI as warning dialogs. The settings dialog must not crash if a file disappears during scanning or deletion.

## UI

`AdvancedSettingsDialog` gets a `缓存管理` tab. The top row shows:

- cache root path
- total size
- total file count
- `打开缓存目录`
- `刷新`
- `清理 N 天以前`
- `清空全部`

The category table shows category name, path summary, formatted size, file count, and actions:

- `打开`: opens the first path for that category, creating it first when needed
- `清空`: asks for confirmation, clears only that category, then refreshes statistics

## Testing

- Unit tests cover category statistics, aggregate totals, other-cache detection, clearing one category, and clearing all cache.
- UI tests cover the new tab, total/category labels, refresh behavior, and clear-category wiring.
- UI tests cover age-based cleanup wiring and refreshed totals.
