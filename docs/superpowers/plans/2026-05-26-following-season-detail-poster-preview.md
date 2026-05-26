# Following Season Detail Poster Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the middle season-detail info stack to show title, episode count, and air date top-aligned in that order, and make the middle-pane season poster open a large preview dialog when clicked.

**Architecture:** Keep the existing three-pane `FollowingEpisodeBrowser` structure and the already-implemented official-style season detail pane, but refine its top-row ordering/alignment and add a dedicated season-poster preview dialog patterned after the existing episode preview dialog approach. Reuse current poster loading utilities and keep the new interaction local to the middle pane.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

## File Map

- Modify: `src/atv_player/ui/following_episode_browser.py`
  - Owns middle-pane season detail widgets, their ordering/alignment, and poster click interaction.
- Modify: `tests/test_following_episode_browser.py`
  - Covers middle-pane layout ordering, top alignment, and poster-preview activation.

---

### Task 1: Reorder And Top-Align The Season Detail Info Stack

**Files:**
- Modify: `tests/test_following_episode_browser.py`
- Modify: `src/atv_player/ui/following_episode_browser.py`

- [ ] **Step 1: Write the failing layout-order test**

Add a focused browser test that locks the text order to title -> episode count -> air date and verifies the stack is top-aligned.

```python
def test_following_episode_browser_places_title_count_and_air_date_at_top(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)

    assert browser.season_detail_info_layout.itemAt(0).widget() is browser.season_detail_title_label
    assert browser.season_detail_info_layout.itemAt(1).widget() is browser.season_detail_episode_count_label
    assert browser.season_detail_info_layout.itemAt(2).widget() is browser.season_detail_air_date_label
    assert browser.season_detail_info_layout.itemAt(3).spacerItem() is not None
```

- [ ] **Step 2: Run the focused layout-order test and verify it fails**

Run: `uv run pytest tests/test_following_episode_browser.py -k "places_title_count_and_air_date_at_top" -q`

Expected: FAIL because the current layout order is title -> air date -> episode count and there is no bottom spacer locking the stack to the top.

- [ ] **Step 3: Write the minimal ordering/alignment implementation**

In `src/atv_player/ui/following_episode_browser.py`, reorder the info-layout widgets and add a trailing stretch/spacer so the labels stay pinned to the top.

```python
self.season_detail_info_layout.addWidget(self.season_detail_title_label)
self.season_detail_info_layout.addWidget(self.season_detail_episode_count_label)
self.season_detail_info_layout.addWidget(self.season_detail_air_date_label)
self.season_detail_info_layout.addStretch(1)
```

Keep refresh logic aligned with that order:

```python
self.season_detail_title_label.setText(summary.title or "未命名季")
self.season_detail_episode_count_label.setText(
    f"共 {summary.episode_count} 集" if summary.episode_count > 0 else ""
)
self.season_detail_air_date_label.setText(summary.air_date or "")
```

- [ ] **Step 4: Run the focused layout-order test and verify it passes**

Run: `uv run pytest tests/test_following_episode_browser.py -k "places_title_count_and_air_date_at_top" -q`

Expected: PASS

- [ ] **Step 5: Commit the info-stack refinement**

```bash
git add tests/test_following_episode_browser.py src/atv_player/ui/following_episode_browser.py
git commit -m "feat: top-align season detail metadata stack"
```

---

### Task 2: Add Middle-Pane Season Poster Preview Dialog

**Files:**
- Modify: `tests/test_following_episode_browser.py`
- Modify: `src/atv_player/ui/following_episode_browser.py`

- [ ] **Step 1: Write the failing poster-preview tests**

Add one test for the click path and one test for the no-poster guard.

```python
def test_following_episode_browser_opens_large_preview_from_season_poster_click(qtbot, monkeypatch) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=2, title="S2E1")],
            seasons=[
                FollowingSeason(
                    season_number=2,
                    title="第二季",
                    poster="poster-2",
                    episode_count=8,
                )
            ],
            fallback_season=1,
        ),
        current_episode=0,
        selected_season_number=2,
    )
    opened: list[str] = []
    monkeypatch.setattr(
        "atv_player.ui.following_episode_browser.FollowingSeasonPosterPreviewDialog.exec",
        lambda self_dialog: opened.append(self_dialog.windowTitle()) or 1,
    )

    browser._open_current_season_poster_preview()

    assert opened == ["第二季"]
```

```python
def test_following_episode_browser_skips_poster_preview_when_no_poster_available(qtbot, monkeypatch) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=2, title="S2E1")],
            seasons=[FollowingSeason(season_number=2, title="第二季", episode_count=8)],
            fallback_season=1,
        ),
        current_episode=0,
        selected_season_number=2,
    )
    opened: list[str] = []
    monkeypatch.setattr(
        "atv_player.ui.following_episode_browser.FollowingSeasonPosterPreviewDialog.exec",
        lambda self_dialog: opened.append(self_dialog.windowTitle()) or 1,
    )

    browser._open_current_season_poster_preview()

    assert opened == []
```

- [ ] **Step 2: Run the focused poster-preview tests and verify they fail**

Run: `uv run pytest tests/test_following_episode_browser.py -k "poster_preview" -q`

Expected: FAIL because there is no season-poster preview dialog and no middle-pane click handler yet.

- [ ] **Step 3: Write the minimal poster-preview implementation**

In `src/atv_player/ui/following_episode_browser.py`, add a small clickable label subclass or mouse-release hook and a dedicated season-poster preview dialog that reuses current poster loading helpers.

```python
class SeasonPosterLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
```

Use it in the middle pane:

```python
self.season_detail_poster_label = SeasonPosterLabel("季封面", self.season_detail_panel)
self.season_detail_poster_label.clicked.connect(self._open_current_season_poster_preview)
```

Add the preview dialog:

```python
class FollowingSeasonPosterPreviewDialog(ThemedDialogBase):
    _image_loaded = Signal(QLabel, object)

    def __init__(self, title: str, poster_source: str, parent: QWidget | None = None) -> None:
        super().__init__(title=title or "季封面", parent=parent, resizable=True)
        self._poster_source = poster_source
        layout = self.content_layout()
        self.poster_label = QLabel("季封面", self)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setMinimumSize(640, 360)
        layout.addWidget(self.poster_label)
        self._image_loaded.connect(self._handle_image_loaded)
        self._load_poster()
```

And add the browser-side opener:

```python
def _open_current_season_poster_preview(self) -> None:
    poster_source = str(self._current_season_summary.poster or "").strip()
    if not poster_source:
        return
    FollowingSeasonPosterPreviewDialog(
        self._current_season_summary.title or "季封面",
        poster_source,
        self,
    ).exec()
```

- [ ] **Step 4: Run the focused poster-preview tests and verify they pass**

Run: `uv run pytest tests/test_following_episode_browser.py -k "poster_preview" -q`

Expected: PASS

- [ ] **Step 5: Commit the poster-preview feature**

```bash
git add tests/test_following_episode_browser.py src/atv_player/ui/following_episode_browser.py
git commit -m "feat: preview season poster from detail pane"
```

---

### Task 3: Final Regression Verification

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
git add src/atv_player/ui/following_episode_browser.py tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py
git commit -m "test: verify season detail poster preview regression coverage"
```

Only run this commit if verification required a final code or test adjustment after the earlier task commits.
