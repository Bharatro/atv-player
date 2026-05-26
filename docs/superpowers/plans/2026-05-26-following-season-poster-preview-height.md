# Following Season Poster Preview Height Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the season poster preview dialog taller so vertical posters are shown as completely as practical instead of appearing short or overly cropped.

**Architecture:** Keep the existing `FollowingSeasonPosterPreviewDialog` entry point and async poster-loading flow, but adjust the preview container sizing and image-fit behavior to favor portrait poster proportions. The change stays local to `src/atv_player/ui/following_episode_browser.py` and is covered by browser-level tests.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

## File Map

- Modify: `src/atv_player/ui/following_episode_browser.py`
  - Owns the season poster preview dialog sizing, image loading target size, and final pixmap rendering behavior.
- Modify: `tests/test_following_episode_browser.py`
  - Covers the larger preview dimensions and portrait-friendly rendering contract.

---

### Task 1: Define The Taller Poster Preview Contract

**Files:**
- Modify: `tests/test_following_episode_browser.py`
- Modify: `src/atv_player/ui/following_episode_browser.py`

- [ ] **Step 1: Write the failing preview sizing tests**

Add direct dialog tests so the desired portrait-friendly preview contract is explicit.

```python
def test_following_season_poster_preview_dialog_uses_taller_portrait_friendly_canvas(qtbot) -> None:
    dialog = FollowingSeasonPosterPreviewDialog("第二季", "poster")
    qtbot.addWidget(dialog)

    assert dialog.poster_label.minimumWidth() >= 640
    assert dialog.poster_label.minimumHeight() > 360
```

```python
def test_following_season_poster_preview_dialog_scales_loaded_image_to_fit_label_height(qtbot) -> None:
    dialog = FollowingSeasonPosterPreviewDialog("第二季", "poster")
    qtbot.addWidget(dialog)

    image = QImage(600, 900, QImage.Format.Format_RGB32)
    dialog._handle_image_loaded(dialog.poster_label, image)

    pixmap = dialog.poster_label.pixmap()
    assert pixmap is not None
    assert pixmap.height() <= dialog.poster_label.height() or dialog.poster_label.minimumHeight()
```

- [ ] **Step 2: Run the focused preview sizing tests and verify they fail**

Run: `uv run pytest tests/test_following_episode_browser.py -k "season_poster_preview_dialog_uses_taller_portrait_friendly_canvas or season_poster_preview_dialog_scales_loaded_image_to_fit_label_height" -q`

Expected: FAIL because the preview is still using `640x360` and the loaded image is not explicitly scaled for the portrait-friendly target.

- [ ] **Step 3: Write the minimal taller-preview implementation**

In `src/atv_player/ui/following_episode_browser.py`, increase the preview label height and make the loaded image scale to fit while preserving aspect ratio.

```python
self.poster_label.setMinimumSize(720, 960)
```

If that is too tall for the current dialog shell, use a slightly smaller portrait-friendly floor, but keep the height substantially above `360`.

Update the image-loaded handler to scale the pixmap against the label target size before assigning it:

```python
target_size = self.poster_label.size()
if target_size.isEmpty():
    target_size = self.poster_label.minimumSize()

pixmap = QPixmap.fromImage(image).scaled(
    target_size,
    Qt.AspectRatioMode.KeepAspectRatio,
    Qt.TransformationMode.SmoothTransformation,
)
self.poster_label.setPixmap(pixmap)
```

If needed, mirror that same target size decision in `_load_poster()`:

```python
target_size = self.poster_label.minimumSize()
if target_size.isEmpty():
    target_size = QSize(480, 720)
```

- [ ] **Step 4: Run the focused preview sizing tests and verify they pass**

Run: `uv run pytest tests/test_following_episode_browser.py -k "season_poster_preview_dialog_uses_taller_portrait_friendly_canvas or season_poster_preview_dialog_scales_loaded_image_to_fit_label_height" -q`

Expected: PASS

- [ ] **Step 5: Commit the taller preview dialog change**

```bash
git add tests/test_following_episode_browser.py src/atv_player/ui/following_episode_browser.py
git commit -m "feat: enlarge season poster preview for portrait posters"
```

---

### Task 2: Final Regression Verification

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
git add src/atv_player/ui/following_episode_browser.py tests/test_following_episode_browser.py
git commit -m "test: verify season poster preview height regression coverage"
```

Only run this commit if verification required a final code or test adjustment after the earlier task commit.
