# Following Season Detail Official Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the middle season-detail pane to use the approved official-style layout and restore runtime in the episode preview dialog metadata row.

**Architecture:** Keep the existing three-pane `FollowingEpisodeBrowser` shell intact, but replace the middle pane's internal widget tree with a top-row poster/info split plus a full-width overview block. Extend `FollowingEpisodePreviewDialog` metadata formatting in place so runtime is rendered on the same line as air date without changing dialog structure.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

## File Map

- Modify: `src/atv_player/ui/following_episode_browser.py`
  - Owns the middle season-detail pane widget tree and season-summary refresh logic.
- Modify: `src/atv_player/ui/following_detail_page.py`
  - Owns `FollowingEpisodePreviewDialog`, where preview metadata text is formatted.
- Modify: `tests/test_following_episode_browser.py`
  - Browser-level layout and season-detail rendering assertions.
- Modify: `tests/test_following_detail_page_ui.py`
  - Preview-dialog metadata assertions and detail-page integration assertions.

---

### Task 1: Refactor Middle Season Detail Pane Layout

**Files:**
- Modify: `tests/test_following_episode_browser.py`
- Modify: `src/atv_player/ui/following_episode_browser.py`

- [ ] **Step 1: Write the failing browser layout test**

Add a new browser test that asserts the middle pane exposes separate date/count labels and a nested top-row layout.

```python
def test_following_episode_browser_uses_official_style_season_detail_layout(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=2, title="S2E1")],
            seasons=[
                FollowingSeason(
                    season_number=2,
                    title="第二季",
                    overview="第二季简介",
                    poster="poster-2",
                    air_date="2026-05-13",
                    episode_count=24,
                )
            ],
            fallback_season=1,
        ),
        current_episode=0,
        selected_season_number=2,
    )

    assert browser.season_detail_poster_label.minimumWidth() > 96
    assert browser.season_detail_top_row.parent() is browser.season_detail_panel
    assert browser.season_detail_info_layout.count() == 3
    assert browser.season_detail_air_date_label.text() == "2026-05-13"
    assert browser.season_detail_episode_count_label.text() == "共 24 集"
    assert browser.season_detail_overview_label.text() == "第二季简介"
```

- [ ] **Step 2: Run the focused browser test and verify it fails**

Run: `uv run pytest tests/test_following_episode_browser.py -k "official_style_season_detail_layout" -q`

Expected: FAIL because `season_detail_top_row`, `season_detail_info_layout`, `season_detail_air_date_label`, and `season_detail_episode_count_label` do not exist yet.

- [ ] **Step 3: Write the minimal season-detail layout implementation**

In `src/atv_player/ui/following_episode_browser.py`, replace the old vertical-stack construction with dedicated top-row widgets and split metadata labels.

```python
self.season_detail_title_label = QLabel("", self.season_detail_panel)
self.season_detail_air_date_label = QLabel("", self.season_detail_panel)
self.season_detail_episode_count_label = QLabel("", self.season_detail_panel)
self.season_detail_overview_label = QLabel("", self.season_detail_panel)

self.season_detail_poster_label.setMinimumSize(128, 182)
self.season_detail_poster_label.setMaximumSize(128, 182)

self.season_detail_top_row = QWidget(self.season_detail_panel)
self.season_detail_info_layout = QVBoxLayout()
self.season_detail_info_layout.setContentsMargins(0, 0, 0, 0)
self.season_detail_info_layout.setSpacing(6)
self.season_detail_info_layout.addWidget(self.season_detail_title_label)
self.season_detail_info_layout.addWidget(self.season_detail_air_date_label)
self.season_detail_info_layout.addWidget(self.season_detail_episode_count_label)

top_row_layout = QHBoxLayout(self.season_detail_top_row)
top_row_layout.setContentsMargins(0, 0, 0, 0)
top_row_layout.setSpacing(14)
top_row_layout.addWidget(self.season_detail_poster_label, 0, Qt.AlignmentFlag.AlignTop)
top_row_layout.addLayout(self.season_detail_info_layout, 1)

season_detail_layout = QVBoxLayout(self.season_detail_panel)
season_detail_layout.setContentsMargins(10, 10, 10, 10)
season_detail_layout.setSpacing(12)
season_detail_layout.addWidget(self.season_detail_top_row)
season_detail_layout.addWidget(self.season_detail_overview_label)
season_detail_layout.addStretch(1)
```

Update season refresh logic to populate the new labels:

```python
self.season_detail_title_label.setText(summary.title or "未命名季")
self.season_detail_air_date_label.setText(summary.air_date or "")
self.season_detail_episode_count_label.setText(
    f"共 {summary.episode_count} 集" if summary.episode_count > 0 else ""
)
self.season_detail_overview_label.setText(summary.overview or "暂无本季简介")
```

Remove the old combined metadata helper once nothing references it:

```python
def _season_summary_episode_count_text(summary: EpisodeSeasonSummary) -> str:
    return f"共 {summary.episode_count} 集" if summary.episode_count > 0 else ""
```

- [ ] **Step 4: Run the focused browser test and verify it passes**

Run: `uv run pytest tests/test_following_episode_browser.py -k "official_style_season_detail_layout" -q`

Expected: PASS

- [ ] **Step 5: Commit the layout refactor**

```bash
git add tests/test_following_episode_browser.py src/atv_player/ui/following_episode_browser.py
git commit -m "feat: adopt official season detail middle-pane layout"
```

---

### Task 2: Preserve Existing Season-Selection Integration With New Labels

**Files:**
- Modify: `tests/test_following_episode_browser.py`
- Modify: `tests/test_following_detail_page_ui.py`
- Modify: `src/atv_player/ui/following_episode_browser.py`

- [ ] **Step 1: Write failing integration assertions for the new labels**

Extend existing season-switching tests to assert the new dedicated labels update correctly.

```python
assert browser.season_detail_air_date_label.text() == ""
assert browser.season_detail_episode_count_label.text() == "共 6 集"
```

And in the detail-page integration test:

```python
assert page.episode_browser.season_detail_title_label.text() == "第二季"
assert page.episode_browser.season_detail_air_date_label.text() == ""
assert page.episode_browser.season_detail_episode_count_label.text() == "共 1 集"
assert "第二季简介" in page.episode_browser.season_detail_overview_label.text()
```

- [ ] **Step 2: Run the focused integration tests and verify they fail**

Run: `uv run pytest tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py -k "season_detail_panel_on_selection or updates_middle_pane_when_switching_season" -q`

Expected: FAIL because the new label assertions are not satisfied yet or because the tests still reference the removed combined metadata arrangement.

- [ ] **Step 3: Write the minimal integration cleanup**

Adjust any existing helper logic in `src/atv_player/ui/following_episode_browser.py` so all season changes continue to update the new fields.

```python
summary = self._current_season_summary
self.season_detail_title_label.setText(summary.title or "未命名季")
self.season_detail_air_date_label.setText(summary.air_date or "")
self.season_detail_episode_count_label.setText(
    f"共 {summary.episode_count} 集" if summary.episode_count > 0 else ""
)
self.season_detail_overview_label.setText(summary.overview or "暂无本季简介")
```

If an old helper remains, delete it instead of keeping dead formatting code:

```python
-def _season_summary_meta_text(summary: EpisodeSeasonSummary) -> str:
-    ...
```

- [ ] **Step 4: Run the focused integration tests and verify they pass**

Run: `uv run pytest tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py -k "season_detail_panel_on_selection or updates_middle_pane_when_switching_season" -q`

Expected: PASS

- [ ] **Step 5: Commit the season-selection integration update**

```bash
git add tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py src/atv_player/ui/following_episode_browser.py
git commit -m "test: cover season detail split metadata labels"
```

---

### Task 3: Restore Runtime In Episode Preview Dialog Metadata Row

**Files:**
- Modify: `tests/test_following_detail_page_ui.py`
- Modify: `src/atv_player/ui/following_detail_page.py`

- [ ] **Step 1: Write the failing preview metadata test**

Add a direct dialog test so runtime formatting is verified without needing to click through the whole page.

```python
def test_following_episode_preview_dialog_shows_air_date_and_runtime_on_same_line(qtbot) -> None:
    dialog = FollowingEpisodePreviewDialog(
        FollowingEpisode(
            episode_number=3,
            title="第三集",
            air_date="2026-05-13",
            runtime=24,
        )
    )
    qtbot.addWidget(dialog)

    assert dialog.meta_label.text() == "2026-05-13 · 24m"
```

Also add the missing-runtime fallback test:

```python
def test_following_episode_preview_dialog_omits_runtime_separator_when_runtime_missing(qtbot) -> None:
    dialog = FollowingEpisodePreviewDialog(
        FollowingEpisode(
            episode_number=3,
            title="第三集",
            air_date="2026-05-13",
            runtime=0,
        )
    )
    qtbot.addWidget(dialog)

    assert dialog.meta_label.text() == "2026-05-13"
```

- [ ] **Step 2: Run the focused preview tests and verify they fail**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "preview_dialog_shows_air_date_and_runtime_on_same_line or omits_runtime_separator_when_runtime_missing" -q`

Expected: FAIL because `FollowingEpisodePreviewDialog` currently sets `meta_label` to `episode.air_date` only.

- [ ] **Step 3: Write the minimal preview metadata implementation**

In `src/atv_player/ui/following_detail_page.py`, replace the direct `episode.air_date` usage with a helper that joins date and runtime safely.

```python
self.meta_label = QLabel(_episode_preview_meta_text(episode), self)
```

Add the helper near the other local formatting helpers:

```python
def _episode_preview_meta_text(episode: FollowingEpisode) -> str:
    parts = []
    if episode.air_date:
        parts.append(episode.air_date)
    if episode.runtime > 0:
        parts.append(f"{episode.runtime}m")
    return " · ".join(parts)
```

- [ ] **Step 4: Run the focused preview tests and verify they pass**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "preview_dialog_shows_air_date_and_runtime_on_same_line or omits_runtime_separator_when_runtime_missing" -q`

Expected: PASS

- [ ] **Step 5: Commit the preview metadata fix**

```bash
git add tests/test_following_detail_page_ui.py src/atv_player/ui/following_detail_page.py
git commit -m "fix: restore runtime in episode preview metadata"
```

---

### Task 4: Final Regression Verification

**Files:**
- Modify: none
- Test: `tests/test_following_episode_browser.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Run browser coverage**

Run: `uv run pytest tests/test_following_episode_browser.py -q`

Expected: PASS

- [ ] **Step 2: Run detail-page coverage**

Run: `uv run pytest tests/test_following_detail_page_ui.py -q`

Expected: PASS

- [ ] **Step 3: Run the combined regression set**

Run: `uv run pytest tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py -q`

Expected: PASS

- [ ] **Step 4: Inspect git status before handoff**

Run: `git status --short`

Expected:

```text
<no output>
```

or only the intended modified files before the final commit if this task is run before batching commits.

- [ ] **Step 5: Commit any final cleanups if needed**

```bash
git add src/atv_player/ui/following_episode_browser.py src/atv_player/ui/following_detail_page.py tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py
git commit -m "test: verify season detail layout regression coverage"
```

Only run this commit if verification required a final code or test adjustment after the earlier task commits.
