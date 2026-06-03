# Homepage Modes Design (首页模式)

## Goal

Let users switch the main window between five homepage presentations from a single
setting: **Browse** (浏览, current default), **Classic/TvBox** (经典), **Simplified/Search**
(精简), **Media/Emby** (媒体), and **TV/Live** (电视). Modes rearrange existing pages and
data; no new backend.

## Scope

In scope:

- New persisted setting `home_mode` and a selector in 高级设置 that applies live.
- A central `apply_home_mode()` that reconfigures the main window per mode.
- All five modes (Browse is the existing behavior).
- One `PosterGridPage` presentation option (categories as top tabs) for Classic.
- Two new composed pages: `SimplifiedHomePage`, `MediaHomePage`.
- An in-player live source/channel switcher for TV mode, reusing the player's playlist panel.

Out of scope:

- New live/search/recommendation backends — modes only read existing controllers.
- Future modes listed in TODO (音乐 / 电台 / TV UI / 遥控器 / 沙发).
- A full remote-control UX beyond the TV switcher panel.

## Mode Selector & Framework

- Add `AppConfig.home_mode: str = "browse"` (`models.py`). Persist it in the SQLite
  `app_config` table mirroring `global_search_hot_source`: schema default
  (`storage.py:486`), `ALTER TABLE` migration (`storage.py:~778`), read
  (`storage.py:~1210`), write (`storage.py:~1402`). Valid values:
  `browse | classic | simplified | media | tv`; unknown → `browse`.
- 高级设置 (`advanced_settings_dialog.py`): a combobox (浏览 / 经典 / 精简 / 媒体 / 电视).
  On change → `save_config` + `MainWindow.apply_home_mode(mode)` (live, no restart).
- Central area: the content container currently stacks `header_layout` + status label +
  `nav_tabs` (`main_window.py:1769-1774`). Wrap the `nav_tabs` slot in a
  `QStackedWidget` (`_home_stack`) whose pages are: `nav_tabs` (Browse), `SimplifiedHomePage`,
  `MediaHomePage`. Classic reuses `nav_tabs` with its tab bar hidden. TV shows no central
  page (it hides the window and drives the player).
- `apply_home_mode(mode)` is the single entry point. It (a) selects the `_home_stack` page,
  (b) toggles header chrome (search box / action icons / nav tab bar), and (c) for
  Classic/TV performs mode-specific setup. Called once at startup from `config.home_mode`
  and again on each settings change.

## Modes

### Browse (浏览) — default

`_home_stack` shows `nav_tabs`; full header; `_refresh_navigation_tabs()`
(`main_window.py:2236`) unchanged. This is today's behavior.

### Classic (经典 / TvBox)

- Show a single source full-window; the source's **categories become the top tab bar**.
- `PosterGridPage` gains a `category_layout` option (`"list"` default | `"tabs"`). In
  `"tabs"` mode it renders categories as a horizontal `QTabBar` above the grid and hides the
  left `category_list` (reusing the existing `_sync_category_list_visibility` hook,
  `poster_grid_page.py:772`); selecting a category tab calls the existing `load_items`.
- A **source-picker** control (enabled source/plugin tabs, the same set shown in Browse)
  selects the active source; default = last-used source, persisted. Switching reloads
  categories and rebuilds the category tab bar.
- Keep the header global search, the page's in-source keyword search (`search_enabled=True`,
  e.g. `main_window.py:1453`), and the filter panel. The `nav_tabs` tab bar is hidden
  (source-picker + category tabs replace it).
- Many categories overflow horizontally → reuse the existing tab-overflow pattern
  (`plugin_overflow_button`).

### Simplified (精简 / Search)

- New `SimplifiedHomePage` shown via `_home_stack`. Hide the `nav_tabs` and the header's own
  search box; keep header action icons (⚙ 高级设置, logout) so the mode stays switchable.
- A prominent centered search box that funnels into the existing global search
  (`_start_global_search`).
- **热搜词** chips from the existing hot-keyword feed (`load_360_hot_searches` /
  `load_tencent_hot_searches`, `main_window.py:408` / `:433`); clicking a word fills the
  query and runs the global search.
- **热门推荐** poster grid from the Douban hot/recommended list (douban controller); clicking
  a poster fills the query with its title and runs the global search.

### Media (媒体 / Emby)

- New `MediaHomePage` shown via `_home_stack`: a **resume hero** (当前播放 = the most recent
  in-progress item, from history / `last_playback_*`) followed by three horizontal rows —
  **继续观看** (continue-watching history), **追剧** (following), **收藏** (favorites).
- Rows reuse the existing history (with the `continue_watching` filter), following, and
  favorites controllers/data. Clicking: hero / continue-watching → resume playback;
  following → following detail; favorite → favorite detail.
- Empty hero (nothing in progress) shows a "继续浏览" call-to-action instead of a blank hero;
  empty rows show per-row empty states.

### TV (电视 / Live)

- On enter (every launch while `home_mode == tv`, and immediately when switched in from
  settings): pick the default live source — `LiveSourceConfig` with `is_default`, else the
  lowest `sort_order` among enabled sources. Resolve its **first playable channel**: iterate
  channels in order (descending into the first group if grouped, via
  `custom_live_service` `load_items`/`load_folder_items`), **skipping entries whose
  `stream_url` is not a real stream** (`_looks_like_stream_url`, `live_controller.py:8`;
  notices/placeholders). Build the request (`live_controller.build_request`) and open the
  `PlayerWindow`. **Hide the main window** while playing.
- **In-player switcher:** reuse the player's existing side playlist panel
  (`player_window.py:899/906`). The `playlist_source_combo` lists enabled live sources
  (switch source → load + play its first valid channel); the `playlist` list shows the
  current source's channels (click → play). No window close needed.
- Fallback: if no playable channel exists in any enabled source, reveal the main window on
  the 网络直播 tab and show a brief notice.

## Data Flow

Modes are presentation-only and read existing controllers. Hot-keyword, Douban, and
dashboard data are fetched off the UI thread using the existing `AsyncGuard` patterns; live
channel resolution uses the existing live controller / custom live service. No schema change
beyond the single `home_mode` column.

## Error Handling & Empty States

- Missing history/following/favorites → per-row empty states; empty hero → CTA.
- Hot-keyword / Douban fetch failure → empty section, no crash (existing async guards).
- TV: no playable channel → main window + live tab + notice (above).
- Unknown/legacy `home_mode` value → treated as `browse`.

## Testing

Unit (pure logic):

- `home_mode` round-trips through `save_config`/`load_config` and the migration; default and
  unknown values resolve to `browse`.
- First-playable-channel selection skips non-stream/notice entries and picks the first valid
  channel; default-source selection honors `is_default` then `sort_order`.
- Mode → visibility mapping (which chrome/tabs each mode shows).

Widget/smoke (follow existing `tests/` patterns):

- `apply_home_mode` switches the `_home_stack` page and toggles expected widgets for each
  mode.
- `PosterGridPage` `category_layout="tabs"` renders a category tab bar, hides the left list,
  and category selection drives `load_items`.
- `SimplifiedHomePage`: clicking a hot word / recommendation fills the query and triggers the
  global search.

## Build Phases

1. **Framework** — `home_mode` config + migration, advanced-settings selector,
   `_home_stack`, `apply_home_mode()` (Browse working end-to-end).
2. **Media** — `MediaHomePage`.
3. **Simplified** — `SimplifiedHomePage`.
4. **Classic** — `PosterGridPage` `category_layout="tabs"` + source-picker.
5. **TV** — default-source/first-channel resolution, hide-window auto-play, in-player switcher.

## Assumptions

1. Classic hides the `nav_tabs` tab bar entirely (source-picker + category tabs only).
2. Media empty hero shows a "继续浏览" CTA rather than a blank hero.
3. Simplified hides nav tabs and the header search box, keeps the header action icons.
4. TV auto-plays on every launch in TV mode and immediately on switch-in from settings.
