# Metadata ID Link Styling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make player detail metadata IDs render as clickable external links, including IMDb, and give those links a clearer shared visual style.

**Architecture:** Keep external metadata URL inference centralized in `PlayerWindow._external_metadata_url()`, and keep detail rendering inside the existing `QTextBrowser` HTML pipeline. Add a small HTML helper for styled metadata ID links so the behavior stays local to the player detail view.

**Tech Stack:** Python 3, PySide6, pytest, pytest-qt

---

## File Map

- Modify: `tests/test_player_window_ui.py`
  - add regression coverage for IMDb URL mapping and link styling markers
- Modify: `src/atv_player/ui/player_window.py`
  - add IMDb external URL mapping
  - add shared HTML helper/class for styled metadata ID links
  - reuse the helper from metadata rows and detail fields

### Task 1: Lock The New Behavior With Tests

**Files:**
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing UI regression test**

```python
def test_player_window_renders_external_metadata_links_for_known_ids(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            category_name="动漫",
            dbid=30318230,
            detail_fields=[
                PlaybackDetailField(label="TMDB ID", value="76479"),
                PlaybackDetailField(label="Bangumi ID", value="526975"),
                PlaybackDetailField(label="IMDb ID", value="tt28489780"),
            ],
        ),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(session)

    html = window.metadata_view.toHtml()
    assert "https://movie.douban.com/subject/30318230/" in html
    assert "https://www.themoviedb.org/tv/76479" in html
    assert "https://bgm.tv/subject/526975" in html
    assert "https://www.imdb.com/title/tt28489780" in html
    assert "metadata-external-link" in html
```

- [ ] **Step 2: Run the focused UI test and verify RED**

Run: `uv run pytest tests/test_player_window_ui.py -k "renders_external_metadata_links_for_known_ids" -v`

Expected: FAIL because `IMDb ID` is not mapped and the HTML does not yet include the new style marker.

### Task 2: Implement The Smallest Rendering Change

**Files:**
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Add IMDb URL mapping**

```python
if normalized_target == "imdb" or normalized_label == "imdb id":
    return f"https://www.imdb.com/title/{text}"
```

- [ ] **Step 2: Add a shared styled-link HTML helper**

```python
def _metadata_external_link_html(self, url: str, label: str) -> str:
    return (
        f'<a class="metadata-external-link" href="{html.escape(url)}">'
        f"{html.escape(label)}"
        "</a>"
    )
```

- [ ] **Step 3: Reuse the helper from metadata row and detail field rendering**

```python
if url:
    return f"{html.escape(label)}: {self._metadata_external_link_html(url, text)}".rstrip()
```

- [ ] **Step 4: Keep styling local to the rendered HTML**

```python
style = (
    "<style>"
    "a.metadata-external-link { color: #8f5a32; text-decoration: underline; font-weight: 600; }"
    "a.metadata-external-link:hover { color: #b46b37; }"
    "</style>"
)
```

- [ ] **Step 5: Run the focused UI test and verify GREEN**

Run: `uv run pytest tests/test_player_window_ui.py -k "renders_external_metadata_links_for_known_ids" -v`

Expected: PASS

### Task 3: Run Broader Regression Coverage

**Files:**
- Modify: none

- [ ] **Step 1: Run the player-window metadata link tests**

Run: `uv run pytest tests/test_player_window_ui.py -k "metadata_link or external_metadata_links or renders_link_action_id_as_external_url" -v`

Expected: PASS with existing external-link and action-link behavior preserved.

## Self-Review

- Spec coverage: includes IMDb mapping, existing ID link preservation, scoped styling, and external-link click behavior
- Placeholder scan: no TODO/TBD placeholders remain
- Type consistency: plan only touches existing `PlayerWindow` HTML helpers and test names already present in the suite
