# Plugin Manager Filter Bar Style Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the plugin manager filter bar with the existing `HistoryPage` filter-bar pattern so its search box, filter combos, and layout behave like the app's established `FlatComboBox`-based UI.

**Architecture:** Keep all behavioral logic in `PluginManagerDialog` unchanged and limit the work to the condition-bar presentation layer. Reuse the existing `FlatComboBox` widget and the same combo sizing rules used by `HistoryPage`, then verify the final row still preserves the plugin-manager search/filter/sort behavior.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

## File Structure

- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
  - Replace the two raw `QComboBox` instances with `FlatComboBox`, add a local combo-width helper mirroring `HistoryPage`, and align the filter-row styling/layout with the existing app pattern.
- Modify: `tests/test_plugin_manager_dialog.py`
  - Extend the existing dialog suite with style/layout assertions for `FlatComboBox`, combo width policy, search field styling, and responsive width relationships.

### Task 1: Replace Raw Combo Boxes With The Shared Filter Combo Pattern

**Files:**
- Modify: [src/atv_player/ui/plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:1)
- Test: [tests/test_plugin_manager_dialog.py](/home/harold/workspace/atv-player/tests/test_plugin_manager_dialog.py:183)

- [ ] **Step 1: Write the failing combo-style tests**

Update `test_plugin_manager_dialog_renders_search_filter_sort_controls` in `tests/test_plugin_manager_dialog.py` so it verifies the new combo component type and width strategy:

```python
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QLabel, QSizePolicy

from atv_player.ui.theme import FlatComboBox
```

Then change the test body to:

```python
def test_plugin_manager_dialog_renders_search_filter_sort_controls(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.search_input.placeholderText() == "搜索名称或地址"
    assert isinstance(dialog.enabled_filter_combo, FlatComboBox)
    assert dialog.enabled_filter_combo.currentText() == "全部"
    assert dialog.enabled_filter_combo.sizeAdjustPolicy() == QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    assert dialog.enabled_filter_combo.minimumContentsLength() == 6
    assert dialog.enabled_filter_combo.maxVisibleItems() == 12
    assert dialog.enabled_filter_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Preferred
    assert isinstance(dialog.sort_combo, FlatComboBox)
    assert dialog.sort_combo.currentText() == "当前顺序"
    assert dialog.sort_combo.sizeAdjustPolicy() == QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    assert dialog.sort_combo.minimumContentsLength() == 6
    assert dialog.sort_combo.maxVisibleItems() == 12
    assert dialog.sort_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Preferred
    assert dialog.clear_filters_button.text() == "清空"
```

Add a new width-calculation test directly below it:

```python
def test_plugin_manager_dialog_filter_combos_reserve_minimum_width_for_longest_label(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    for combo in (dialog.enabled_filter_combo, dialog.sort_combo):
        longest_label_width = max(combo.fontMetrics().horizontalAdvance(combo.itemText(index)) for index in range(combo.count()))
        left_padding = int(combo.property("flat_combo_left_padding") or 12)
        indicator_padding = int(combo.property("flat_combo_indicator_padding") or 40)
        assert combo.minimumWidth() >= longest_label_width + left_padding + indicator_padding
```

- [ ] **Step 2: Run the focused combo tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "renders_search_filter_sort_controls or filter_combos_reserve_minimum_width_for_longest_label" -v
```

Expected: `FAIL` because `PluginManagerDialog` still creates raw `QComboBox` instances and does not yet configure their width policy like `HistoryPage`.

- [ ] **Step 3: Replace the combo widgets and add the shared sizing helper**

In `src/atv_player/ui/plugin_manager_dialog.py`, update the imports to pull in the shared theme utilities:

```python
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from atv_player.ui.theme import (
    FlatComboBox,
    build_placeholder_label_qss,
    build_search_line_edit_qss,
    current_tokens,
)
```

Replace the combo construction in `__init__` with:

```python
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("搜索名称或地址")
        self.enabled_filter_combo = FlatComboBox(self)
        self.enabled_filter_combo.addItem("全部", "all")
        self.enabled_filter_combo.addItem("仅启用", "enabled")
        self.enabled_filter_combo.addItem("仅禁用", "disabled")
        self.sort_combo = FlatComboBox(self)
        self.sort_combo.addItem("当前顺序", "sort_order")
        self.sort_combo.addItem("名称", "name")
        self.sort_combo.addItem("最近加载", "last_loaded_at")
```

Immediately after the combo items are added, configure them with a new private helper:

```python
        self._configure_filter_combo(self.enabled_filter_combo, minimum_contents_length=6)
        self._configure_filter_combo(self.sort_combo, minimum_contents_length=6)
```

Add this helper near `_clear_view_filters(...)` so it mirrors the `HistoryPage` rule set:

```python
    def _configure_filter_combo(self, combo: QComboBox, *, minimum_contents_length: int) -> None:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(minimum_contents_length)
        combo.setMaxVisibleItems(12)
        longest_label_width = max(combo.fontMetrics().horizontalAdvance(combo.itemText(index)) for index in range(combo.count()))
        left_padding = int(combo.property("flat_combo_left_padding") or 12)
        indicator_padding = int(combo.property("flat_combo_indicator_padding") or 40)
        combo.setMinimumWidth(longest_label_width + left_padding + indicator_padding)
        combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
```

Remove the fixed-width lines:

```python
        self.enabled_filter_combo.setMinimumWidth(112)
        self.sort_combo.setMinimumWidth(128)
```

- [ ] **Step 4: Run the focused combo tests to verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "renders_search_filter_sort_controls or filter_combos_reserve_minimum_width_for_longest_label" -v
```

Expected: `PASS` for the updated control test and the new width-calculation test.

- [ ] **Step 5: Commit the combo alignment work**

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: align plugin manager filter combos"
```

### Task 2: Align Search Field Styling And Filter Bar Layout

**Files:**
- Modify: [src/atv_player/ui/plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:1)
- Test: [tests/test_plugin_manager_dialog.py](/home/harold/workspace/atv-player/tests/test_plugin_manager_dialog.py:183)

- [ ] **Step 1: Write the failing filter-bar layout tests**

Add these tests below the combo width test in `tests/test_plugin_manager_dialog.py`:

```python
def test_plugin_manager_dialog_uses_history_style_search_field_and_spacing(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.search_input.isClearButtonEnabled() is True
    assert dialog.search_input.styleSheet() != ""
    assert dialog.filters_layout.spacing() == 12


def test_plugin_manager_dialog_filter_bar_keeps_search_input_wider_than_filter_combos(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.resize(1200, 520)
    dialog.show()
    qtbot.wait(50)

    assert dialog.search_input.width() > dialog.enabled_filter_combo.width()
    assert dialog.search_input.width() > dialog.sort_combo.width()
```

- [ ] **Step 2: Run the filter-bar layout tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "uses_history_style_search_field_and_spacing or filter_bar_keeps_search_input_wider_than_filter_combos" -v
```

Expected: `FAIL` because the plugin manager search field does not yet enable the clear button or apply the shared search-field stylesheet.

- [ ] **Step 3: Apply the shared search-field styling and finalize the filter bar layout**

In `src/atv_player/ui/plugin_manager_dialog.py`, inside `__init__`, immediately after the search input placeholder:

```python
        tokens = current_tokens()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(build_search_line_edit_qss(tokens))
```

Keep the existing `self.filters_layout = QHBoxLayout()` and finalize the layout rhythm explicitly:

```python
        self.filters_layout = QHBoxLayout()
        self.filters_layout.setSpacing(12)
        self.filters_layout.addWidget(self.search_input, 1)
        self.filters_layout.addWidget(self.enabled_filter_combo)
        self.filters_layout.addWidget(self.sort_combo)
        self.filters_layout.addWidget(self.clear_filters_button)
```

Do not modify any of the following methods during this task:

```python
    def _visible_plugins(self, plugins) -> list:
    def _matches_search(self, plugin, search_term: str) -> bool:
    def _sort_plugins(self, plugins) -> list:
    def _apply_view_filters(self) -> None:
    def _clear_view_filters(self) -> None:
```

- [ ] **Step 4: Run the full plugin manager dialog suite**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -v
```

Expected: `PASS` for the full suite, including the new style/layout assertions and all existing behavior tests for search, filter, sort, clear, and selection restoration.

- [ ] **Step 5: Commit the filter-bar styling work**

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: align plugin manager filter bar styling"
```

## Self-Review

- Spec coverage check:
  - `FlatComboBox` replacement: Task 1
  - Shared combo width strategy: Task 1
  - Search field style alignment: Task 2
  - Unified filter-bar spacing and width relationships: Task 2
  - Existing plugin-manager behavior unchanged: Task 2 full-suite verification
- Placeholder scan:
  - No `TODO` / `TBD`
  - Every code step includes exact code
  - Every verification step includes an exact command and expected result
- Type consistency:
  - Widget names stay consistent with existing code: `search_input`, `enabled_filter_combo`, `sort_combo`, `filters_layout`
  - Shared helper name is consistent across all steps: `_configure_filter_combo`
