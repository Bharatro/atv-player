# Danmaku Count Intro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepend one display-only `X条弹幕来袭！` danmaku message before real danmaku records during subtitle rendering.

**Architecture:** Keep the change inside the danmaku subtitle render pipeline by extending the parsed in-memory record list with one synthetic intro record. This preserves provider payloads, cached XML, and player-window integration while making the feature apply to both SRT and ASS output.

**Tech Stack:** Python, pytest, XML parsing via `xml.etree.ElementTree`

---

### Task 1: Add regression coverage for the intro danmaku

**Files:**
- Modify: `tests/test_danmaku_subtitle.py`
- Test: `tests/test_danmaku_subtitle.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_danmaku_outputs_count_intro_before_real_comments() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="1.0,1,25,16777215">第一条</d>'
        '<d p="2.0,1,25,16777215">第二条</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(xml_text, line_count=2, duration_seconds=4.0)

    assert "2条弹幕来袭！" in subtitle
    assert subtitle.index("2条弹幕来袭！") < subtitle.index("第一条")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_danmaku_subtitle.py::test_render_danmaku_outputs_count_intro_before_real_comments -v`
Expected: FAIL because the renderer does not yet inject the intro danmaku.

### Task 2: Implement the synthetic intro record

**Files:**
- Modify: `src/atv_player/danmaku/subtitle.py`
- Test: `tests/test_danmaku_subtitle.py`

- [ ] **Step 1: Write minimal implementation**

```python
def _with_intro_record(records: list[_ParsedDanmaku]) -> list[_ParsedDanmaku]:
    if not records:
        return []
    intro = _ParsedDanmaku(
        time_offset=max(0.0, records[0].time_offset - 1.0),
        pos=5,
        color="16777215",
        content=f"{len(records)}条弹幕来袭！",
    )
    return [intro, *records]
```

Use the helper from both SRT and ASS render paths after XML parsing and before line assignment.

- [ ] **Step 2: Run the focused test to verify it passes**

Run: `uv run pytest tests/test_danmaku_subtitle.py::test_render_danmaku_outputs_count_intro_before_real_comments -v`
Expected: PASS

### Task 3: Run the subtitle regression subset

**Files:**
- Modify: `src/atv_player/danmaku/subtitle.py`
- Test: `tests/test_danmaku_subtitle.py`

- [ ] **Step 1: Run the subtitle test file**

Run: `uv run pytest tests/test_danmaku_subtitle.py -v`
Expected: PASS

- [ ] **Step 2: Commit**

```bash
git add src/atv_player/danmaku/subtitle.py tests/test_danmaku_subtitle.py docs/superpowers/plans/2026-05-11-danmaku-count-intro.md
git commit -m "feat: prepend danmaku count intro"
```
