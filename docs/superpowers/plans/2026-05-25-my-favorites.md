# My Favorites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local `我的收藏` feature with list-page and player entry points, a dedicated card-based favorites page, reopen routing through original sources, subtle title-change hints, and delete support.

**Architecture:** Use a dedicated SQLite-backed `FavoritesRepository` plus a `FavoritesController` that owns refresh-time `vod_name` comparison and page-level operations. Keep playback reopening in `MainWindow`, keep local favorite persistence separate from source controllers, and build a dedicated `FavoritesPage` card view that follows poster-grid visuals without forcing the feature into `PosterGridPage`.

**Tech Stack:** Python, PySide6, SQLite, pytest, existing `MainWindow`/controller patterns

---

## File Structure

- Create: `src/atv_player/favorites_repository.py`
  Responsibility: local SQLite persistence for favorites, including upsert, paging, search, deletion, favorite lookup, and refresh-state updates.
- Create: `src/atv_player/controllers/favorites_controller.py`
  Responsibility: map repository rows into page view models, refresh latest detail per source, compare `vod_name`, and provide page operations.
- Create: `src/atv_player/ui/favorites_page.py`
  Responsibility: render a dedicated multi-select card page with search, refresh, delete, clear-current-result, pagination, and open signals.
- Modify: `src/atv_player/models.py`
  Responsibility: add favorite record and any lightweight UI model needed by the controller/page.
- Modify: `src/atv_player/ui/browse_page.py`
  Responsibility: add video-row context menu favorite toggles.
- Modify: `src/atv_player/ui/player_window.py`
  Responsibility: add a local favorite icon button in the detail area and keep its state synced with the current item.
- Modify: `src/atv_player/ui/main_window.py`
  Responsibility: create/register the favorites page, add the header icon button between browse/history, and route favorite-open requests through existing source-specific request builders.
- Modify: `src/atv_player/app.py`
  Responsibility: construct/inject repository and controller instances.
- Create: `tests/test_favorites_repository.py`
  Responsibility: repository persistence, upsert, filtering, deletion, and changed-title state.
- Create: `tests/test_favorites_controller.py`
  Responsibility: refresh behavior, `vod_name` comparison, failure fallback, and controller operations.
- Modify: `tests/test_browse_page_ui.py`
  Responsibility: right-click favorite actions on video rows.
- Modify: `tests/test_player_window_ui.py`
  Responsibility: player favorite icon button behavior and placement.
- Modify: `tests/test_main_window_ui.py`
  Responsibility: favorites tab/button registration and open routing.
- Modify: `tests/test_app.py`
  Responsibility: application wiring for repository/controller injection.

## Task 1: Favorite Data Model And Repository

**Files:**
- Modify: `src/atv_player/models.py`
- Create: `src/atv_player/favorites_repository.py`
- Test: `tests/test_favorites_repository.py`

- [ ] **Step 1: Write the failing repository tests**

```python
from pathlib import Path

from atv_player.favorites_repository import FavoritesRepository


def test_favorites_repository_upserts_and_marks_changed_title(tmp_path: Path) -> None:
    repo = FavoritesRepository(tmp_path / "app.db")
    repo.save_favorite(
        {
            "source_kind": "browse",
            "source_key": "",
            "source_name": "文件浏览",
            "vod_id": "detail-1",
            "vod_name_snapshot": "庆余年",
            "latest_vod_name": "庆余年",
            "vod_pic": "poster-a",
            "vod_remarks": "4K",
            "title_changed": False,
            "created_at": 100,
            "updated_at": 100,
        }
    )

    repo.update_refresh_state("browse", "", "detail-1", latest_vod_name="庆余年 第二季", vod_pic="poster-b", vod_remarks="完结")
    records, total = repo.load_page(page=1, size=20, keyword="")

    assert total == 1
    assert records[0].vod_name_snapshot == "庆余年"
    assert records[0].latest_vod_name == "庆余年 第二季"
    assert records[0].title_changed is True


def test_favorites_repository_deletes_selected_and_filtered_rows(tmp_path: Path) -> None:
    repo = FavoritesRepository(tmp_path / "app.db")
    repo.save_favorite(
        {
            "source_kind": "browse",
            "source_key": "",
            "source_name": "文件浏览",
            "vod_id": "detail-1",
            "vod_name_snapshot": "庆余年",
            "latest_vod_name": "庆余年",
            "vod_pic": "",
            "vod_remarks": "",
            "title_changed": False,
            "created_at": 100,
            "updated_at": 100,
        }
    )
    repo.save_favorite(
        {
            "source_kind": "youtube",
            "source_key": "",
            "source_name": "YouTube",
            "vod_id": "yt:video:2",
            "vod_name_snapshot": "吃饭录像",
            "latest_vod_name": "吃饭录像",
            "vod_pic": "",
            "vod_remarks": "",
            "title_changed": False,
            "created_at": 101,
            "updated_at": 101,
        }
    )

    records, _ = repo.load_page(page=1, size=20, keyword="庆")
    repo.delete_favorites(records)
    remaining, total = repo.load_page(page=1, size=20, keyword="")

    assert total == 1
    assert remaining[0].vod_id == "yt:video:2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_favorites_repository.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.favorites_repository'`

- [ ] **Step 3: Add favorite models**

```python
@dataclass(slots=True)
class FavoriteRecord:
    source_kind: str
    source_key: str
    source_name: str
    vod_id: str
    vod_name_snapshot: str
    latest_vod_name: str
    vod_pic: str
    vod_remarks: str
    title_changed: bool
    created_at: int
    updated_at: int


@dataclass(slots=True)
class FavoritePageResult:
    records: list[FavoriteRecord]
    total: int
```

- [ ] **Step 4: Write the minimal repository implementation**

```python
from __future__ import annotations

from pathlib import Path

from atv_player.models import FavoriteRecord
from atv_player.sqlite_utils import managed_connection


class FavoritesRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return managed_connection(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    source_kind TEXT NOT NULL,
                    source_key TEXT NOT NULL DEFAULT '',
                    source_name TEXT NOT NULL DEFAULT '',
                    vod_id TEXT NOT NULL,
                    vod_name_snapshot TEXT NOT NULL DEFAULT '',
                    latest_vod_name TEXT NOT NULL DEFAULT '',
                    vod_pic TEXT NOT NULL DEFAULT '',
                    vod_remarks TEXT NOT NULL DEFAULT '',
                    title_changed INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (source_kind, source_key, vod_id)
                )
                """
            )

    def save_favorite(self, payload: dict[str, object]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO favorites (
                    source_kind, source_key, source_name, vod_id, vod_name_snapshot,
                    latest_vod_name, vod_pic, vod_remarks, title_changed, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_kind, source_key, vod_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    vod_name_snapshot = excluded.vod_name_snapshot,
                    latest_vod_name = excluded.latest_vod_name,
                    vod_pic = excluded.vod_pic,
                    vod_remarks = excluded.vod_remarks,
                    title_changed = excluded.title_changed,
                    updated_at = excluded.updated_at
                """,
                (
                    str(payload.get("source_kind", "")),
                    str(payload.get("source_key", "")),
                    str(payload.get("source_name", "")),
                    str(payload.get("vod_id", "")),
                    str(payload.get("vod_name_snapshot", "")),
                    str(payload.get("latest_vod_name", "")),
                    str(payload.get("vod_pic", "")),
                    str(payload.get("vod_remarks", "")),
                    1 if bool(payload.get("title_changed", False)) else 0,
                    int(payload.get("created_at", 0)),
                    int(payload.get("updated_at", 0)),
                ),
            )

    def update_refresh_state(
        self,
        source_kind: str,
        source_key: str,
        vod_id: str,
        *,
        latest_vod_name: str,
        vod_pic: str,
        vod_remarks: str,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT vod_name_snapshot FROM favorites WHERE source_kind = ? AND source_key = ? AND vod_id = ?",
                (source_kind, source_key, vod_id),
            ).fetchone()
            if row is None:
                return
            snapshot = str(row[0] or "")
            conn.execute(
                """
                UPDATE favorites
                SET latest_vod_name = ?, vod_pic = ?, vod_remarks = ?, title_changed = ?
                WHERE source_kind = ? AND source_key = ? AND vod_id = ?
                """,
                (
                    latest_vod_name,
                    vod_pic,
                    vod_remarks,
                    1 if latest_vod_name != snapshot else 0,
                    source_kind,
                    source_key,
                    vod_id,
                ),
            )

    def load_page(self, *, page: int, size: int, keyword: str) -> tuple[list[FavoriteRecord], int]:
        where_sql = ""
        params: list[object] = []
        if keyword.strip():
            where_sql = "WHERE latest_vod_name LIKE ? OR vod_name_snapshot LIKE ?"
            like = f"%{keyword.strip()}%"
            params.extend([like, like])
        with self._connect() as conn:
            total = int(conn.execute(f"SELECT COUNT(*) FROM favorites {where_sql}", params).fetchone()[0])
            offset = max(page - 1, 0) * size
            rows = conn.execute(
                f"""
                SELECT source_kind, source_key, source_name, vod_id, vod_name_snapshot, latest_vod_name,
                       vod_pic, vod_remarks, title_changed, created_at, updated_at
                FROM favorites
                {where_sql}
                ORDER BY updated_at DESC, created_at DESC, vod_id ASC
                LIMIT ? OFFSET ?
                """,
                [*params, size, offset],
            ).fetchall()
        return ([
            FavoriteRecord(
                source_kind=str(row[0]),
                source_key=str(row[1]),
                source_name=str(row[2]),
                vod_id=str(row[3]),
                vod_name_snapshot=str(row[4]),
                latest_vod_name=str(row[5]),
                vod_pic=str(row[6]),
                vod_remarks=str(row[7]),
                title_changed=bool(row[8]),
                created_at=int(row[9]),
                updated_at=int(row[10]),
            )
            for row in rows
        ], total)

    def delete_favorites(self, records: list[FavoriteRecord]) -> None:
        with self._connect() as conn:
            conn.executemany(
                "DELETE FROM favorites WHERE source_kind = ? AND source_key = ? AND vod_id = ?",
                [(record.source_kind, record.source_key, record.vod_id) for record in records],
            )
```

- [ ] **Step 5: Add the remaining repository helpers required by the spec**

```python
    def is_favorited(self, source_kind: str, source_key: str, vod_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM favorites WHERE source_kind = ? AND source_key = ? AND vod_id = ?",
                (source_kind, source_key, vod_id),
            ).fetchone()
        return row is not None

    def delete_filtered(self, *, keyword: str) -> None:
        normalized = keyword.strip()
        with self._connect() as conn:
            if not normalized:
                conn.execute("DELETE FROM favorites")
                return
            like = f"%{normalized}%"
            conn.execute(
                "DELETE FROM favorites WHERE latest_vod_name LIKE ? OR vod_name_snapshot LIKE ?",
                (like, like),
            )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_favorites_repository.py -v`

Expected: PASS with repository tests green

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/models.py src/atv_player/favorites_repository.py tests/test_favorites_repository.py
git commit -m "feat: add favorites repository"
```

## Task 2: Favorites Controller Refresh Logic

**Files:**
- Create: `src/atv_player/controllers/favorites_controller.py`
- Modify: `src/atv_player/models.py`
- Test: `tests/test_favorites_controller.py`

- [ ] **Step 1: Write the failing controller tests**

```python
from atv_player.controllers.favorites_controller import FavoritesController
from atv_player.favorites_repository import FavoritesRepository
from atv_player.models import FavoriteRecord, VodItem


def test_favorites_controller_refreshes_latest_title_and_marks_changed(tmp_path) -> None:
    repo = FavoritesRepository(tmp_path / "app.db")
    repo.save_favorite(
        {
            "source_kind": "browse",
            "source_key": "",
            "source_name": "文件浏览",
            "vod_id": "detail-1",
            "vod_name_snapshot": "旧标题",
            "latest_vod_name": "旧标题",
            "vod_pic": "poster-a",
            "vod_remarks": "1080P",
            "title_changed": False,
            "created_at": 10,
            "updated_at": 10,
        }
    )

    controller = FavoritesController(
        repo,
        detail_loader_by_source={
            "browse": lambda record: VodItem(vod_id=record.vod_id, vod_name="新标题", vod_pic="poster-b", vod_remarks="完结")
        },
    )

    records, total = controller.load_page(page=1, size=20, keyword="")

    assert total == 1
    assert records[0].latest_vod_name == "新标题"
    assert records[0].title_changed is True


def test_favorites_controller_refresh_failure_keeps_snapshot_data(tmp_path) -> None:
    repo = FavoritesRepository(tmp_path / "app.db")
    repo.save_favorite(
        {
            "source_kind": "youtube",
            "source_key": "",
            "source_name": "YouTube",
            "vod_id": "yt:video:1",
            "vod_name_snapshot": "吃饭录像",
            "latest_vod_name": "吃饭录像",
            "vod_pic": "poster-a",
            "vod_remarks": "",
            "title_changed": False,
            "created_at": 10,
            "updated_at": 10,
        }
    )

    controller = FavoritesController(
        repo,
        detail_loader_by_source={"youtube": lambda _record: (_ for _ in ()).throw(ValueError("boom"))},
    )

    records, total = controller.load_page(page=1, size=20, keyword="")

    assert total == 1
    assert records[0].latest_vod_name == "吃饭录像"
    assert records[0].title_changed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_favorites_controller.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.controllers.favorites_controller'`

- [ ] **Step 3: Add controller-facing view model helpers**

```python
@dataclass(slots=True)
class FavoriteCardItem:
    record: FavoriteRecord
    display_title: str
    source_label: str
    updated_hint: bool
    secondary_text: str
```

- [ ] **Step 4: Write the minimal controller implementation**

```python
from __future__ import annotations

from collections.abc import Callable

from atv_player.models import FavoriteCardItem, FavoriteRecord, VodItem


class FavoritesController:
    def __init__(
        self,
        repository,
        *,
        detail_loader_by_source: dict[str, Callable[[FavoriteRecord], VodItem | None]],
    ) -> None:
        self._repository = repository
        self._detail_loader_by_source = dict(detail_loader_by_source)

    def load_page(self, *, page: int, size: int, keyword: str) -> tuple[list[FavoriteCardItem], int]:
        records, total = self._repository.load_page(page=page, size=size, keyword=keyword)
        refreshed: list[FavoriteCardItem] = []
        for record in records:
            loader = self._detail_loader_by_source.get(record.source_kind)
            latest_record = record
            if loader is not None:
                try:
                    latest_vod = loader(record)
                except Exception:
                    latest_vod = None
                if latest_vod is not None:
                    latest_title = str(latest_vod.vod_name or record.latest_vod_name or record.vod_name_snapshot)
                    latest_pic = str(latest_vod.vod_pic or record.vod_pic)
                    latest_remarks = str(latest_vod.vod_remarks or record.vod_remarks)
                    self._repository.update_refresh_state(
                        record.source_kind,
                        record.source_key,
                        record.vod_id,
                        latest_vod_name=latest_title,
                        vod_pic=latest_pic,
                        vod_remarks=latest_remarks,
                    )
                    latest_record = FavoriteRecord(
                        source_kind=record.source_kind,
                        source_key=record.source_key,
                        source_name=record.source_name,
                        vod_id=record.vod_id,
                        vod_name_snapshot=record.vod_name_snapshot,
                        latest_vod_name=latest_title,
                        vod_pic=latest_pic,
                        vod_remarks=latest_remarks,
                        title_changed=latest_title != record.vod_name_snapshot,
                        created_at=record.created_at,
                        updated_at=record.updated_at,
                    )
            refreshed.append(
                FavoriteCardItem(
                    record=latest_record,
                    display_title=latest_record.latest_vod_name or latest_record.vod_name_snapshot,
                    source_label=latest_record.source_name or latest_record.source_kind,
                    updated_hint=latest_record.title_changed,
                    secondary_text=(
                        f"原收藏标题: {latest_record.vod_name_snapshot}"
                        if latest_record.title_changed and latest_record.vod_name_snapshot
                        else ""
                    ),
                )
            )
        return refreshed, total
```

- [ ] **Step 5: Add controller operations used by the page and entry points**

```python
    def is_favorited(self, *, source_kind: str, source_key: str, vod_id: str) -> bool:
        return self._repository.is_favorited(source_kind, source_key, vod_id)

    def add_favorite(self, payload: dict[str, object]) -> None:
        self._repository.save_favorite(payload)

    def remove_favorite(self, records: list[FavoriteRecord]) -> None:
        self._repository.delete_favorites(records)

    def clear_filtered(self, *, keyword: str) -> None:
        self._repository.delete_filtered(keyword=keyword)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_favorites_controller.py -v`

Expected: PASS with refresh and fallback tests green

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/controllers/favorites_controller.py src/atv_player/models.py tests/test_favorites_controller.py
git commit -m "feat: add favorites controller"
```

## Task 3: Favorites Page Card UI

**Files:**
- Create: `src/atv_player/ui/favorites_page.py`
- Modify: `src/atv_player/ui/theme.py`
- Test: `tests/test_favorites_page_ui.py`

- [ ] **Step 1: Write the failing page tests**

```python
from atv_player.models import FavoriteCardItem, FavoriteRecord
from atv_player.ui.favorites_page import FavoritesPage


def test_favorites_page_renders_cards_and_update_hint(qtbot) -> None:
    class Controller:
        def load_page(self, *, page: int, size: int, keyword: str):
            record = FavoriteRecord(
                source_kind="browse",
                source_key="",
                source_name="文件浏览",
                vod_id="detail-1",
                vod_name_snapshot="旧标题",
                latest_vod_name="新标题",
                vod_pic="",
                vod_remarks="完结",
                title_changed=True,
                created_at=10,
                updated_at=10,
            )
            return [FavoriteCardItem(record=record, display_title="新标题", source_label="文件浏览", updated_hint=True, secondary_text="原收藏标题: 旧标题")], 1

    page = FavoritesPage(Controller())
    qtbot.addWidget(page)
    page.ensure_loaded()

    qtbot.waitUntil(lambda: len(page.card_widgets) == 1)
    assert page.card_widgets[0].title_label.text() == "新标题"
    assert page.card_widgets[0].property("title_changed") is True


def test_favorites_page_delete_selected_calls_controller(qtbot) -> None:
    deleted = []

    class Controller:
        def load_page(self, *, page: int, size: int, keyword: str):
            record = FavoriteRecord(
                source_kind="browse",
                source_key="",
                source_name="文件浏览",
                vod_id="detail-1",
                vod_name_snapshot="庆余年",
                latest_vod_name="庆余年",
                vod_pic="",
                vod_remarks="",
                title_changed=False,
                created_at=10,
                updated_at=10,
            )
            return [FavoriteCardItem(record=record, display_title="庆余年", source_label="文件浏览", updated_hint=False, secondary_text="")], 1

        def remove_favorite(self, records):
            deleted.extend(records)

    page = FavoritesPage(Controller())
    qtbot.addWidget(page)
    page.ensure_loaded()
    qtbot.waitUntil(lambda: len(page.card_widgets) == 1)
    page.card_widgets[0].setChecked(True)
    page.delete_button.click()

    assert [record.vod_id for record in deleted] == ["detail-1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_favorites_page_ui.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.ui.favorites_page'`

- [ ] **Step 3: Build the dedicated card widget and page shell**

```python
class FavoriteCardButton(QPushButton):
    def __init__(self, item: FavoriteCardItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setCheckable(True)
        self.setProperty("title_changed", item.updated_hint)
        self.title_label = QLabel(item.display_title, self)
        self.source_label = QLabel(item.source_label, self)
        self.secondary_label = QLabel(item.secondary_text, self)
        self.updated_icon = QLabel("•", self)
        self.updated_icon.setVisible(item.updated_hint)
```

- [ ] **Step 4: Implement page loading, selection, and pagination**

```python
class FavoritesPage(QWidget, AsyncGuardMixin):
    open_detail_requested = Signal(object)
    unauthorized = Signal()

    def __init__(self, controller) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self.card_widgets: list[FavoriteCardButton] = []
        self.records: list[FavoriteCardItem] = []
        self.current_page = 1
        self.page_size = 20
        self.total_items = 0
        self.search_edit = QLineEdit()
        self.refresh_button = QPushButton("刷新")
        self.delete_button = QPushButton("删除选中")
        self.clear_button = QPushButton("清空当前结果")
        self.page_size_combo = FlatComboBox()
        self.prev_page_button = QPushButton("上一页")
        self.next_page_button = QPushButton("下一页")
        self.page_label = QLabel("第 1 / 1 页")
```

- [ ] **Step 5: Implement card rendering and operations**

```python
    def _render_cards(self, items: list[FavoriteCardItem]) -> None:
        self.records = list(items)
        self.card_widgets = []
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for favorite in items:
            card = FavoriteCardButton(favorite, self.cards_container)
            card.clicked.connect(self._sync_action_state)
            card.doubleClicked.connect(lambda fav=favorite: self.open_detail_requested.emit(fav.record))
            self.cards_layout.addWidget(card)
            self.card_widgets.append(card)
        self._sync_action_state()

    def _selected_records(self) -> list[FavoriteRecord]:
        return [card.item.record for card in self.card_widgets if card.isChecked()]

    def delete_selected(self) -> None:
        records = self._selected_records()
        if not records:
            return
        self.controller.remove_favorite(records)
        self.load_page()

    def clear_current_results(self) -> None:
        self.controller.clear_filtered(keyword=self.search_edit.text())
        self.current_page = 1
        self.load_page()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_favorites_page_ui.py -v`

Expected: PASS with card rendering and delete tests green

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/ui/favorites_page.py src/atv_player/ui/theme.py tests/test_favorites_page_ui.py
git commit -m "feat: add favorites page"
```

## Task 4: Browse And Player Favorite Entry Points

**Files:**
- Modify: `src/atv_player/ui/browse_page.py`
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `src/atv_player/models.py`
- Test: `tests/test_browse_page_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing browse-page context-menu test**

```python
def test_browse_page_video_context_menu_shows_favorite_toggle(qtbot) -> None:
    toggles = []

    class Controller:
        def load_folder(self, path: str, page: int = 1, size: int = 50):
            return [VodItem(vod_id="detail-1", vod_name="庆余年", type=2, path="/庆余年")], 1

    page = BrowsePage(Controller())
    page.set_favorite_handlers(
        is_favorited=lambda item: item.vod_id == "detail-1",
        toggle_favorite=lambda item: toggles.append(item.vod_id),
    )
    qtbot.addWidget(page)
    page.load_path("/")
    qtbot.waitUntil(lambda: page.table.rowCount() == 1)

    menu = page._build_item_context_menu(0)

    assert [action.text() for action in menu.actions()] == ["取消收藏"]
```

- [ ] **Step 2: Write the failing player favorite-button test**

```python
def test_player_window_renders_detail_favorite_icon_button(qtbot) -> None:
    toggled = []
    item = PlayItem(title="庆余年", url="https://media/1.m3u8", vod_id="detail-1")
    request = OpenPlayerRequest(
        vod=VodItem(vod_id="detail-1", vod_name="庆余年"),
        playlist=[item],
        clicked_index=0,
    )
    window = PlayerWindow(
        config=AppConfig(),
        save_config=lambda: None,
        favorite_is_active=lambda current_item: current_item.vod_id == "detail-1",
        favorite_toggle=lambda current_item: toggled.append(current_item.vod_id),
    )
    qtbot.addWidget(window)
    window.open_session(PlayerController().create_session(request))

    assert window.favorite_button.isVisible() is True
    window.favorite_button.click()
    assert toggled == ["detail-1"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_browse_page_ui.py -k "favorite_toggle" -v`

Expected: FAIL with missing `set_favorite_handlers` or `_build_item_context_menu`

Run: `uv run pytest tests/test_player_window_ui.py -k "detail_favorite_icon_button" -v`

Expected: FAIL with unexpected `favorite_is_active` / `favorite_toggle` arguments

- [ ] **Step 4: Add browse-page favorite hooks and context menu**

```python
class BrowsePage(QWidget, AsyncGuardMixin):
    def __init__(self, controller, config=None, save_config=None) -> None:
        ...
        self._favorite_is_active = lambda _item: False
        self._favorite_toggle = lambda _item: None
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_item_context_menu)

    def set_favorite_handlers(self, *, is_favorited, toggle_favorite) -> None:
        self._favorite_is_active = is_favorited
        self._favorite_toggle = toggle_favorite

    def _build_item_context_menu(self, row: int) -> QMenu:
        menu = QMenu(self)
        item = self._item_for_row(row)
        if item is not None and item.type == 2:
            label = "取消收藏" if self._favorite_is_active(item) else "收藏"
            menu.addAction(label, lambda current=item: self._favorite_toggle(current))
        return menu
```

- [ ] **Step 5: Add the player detail favorite icon button**

```python
class PlayerWindow(...):
    def __init__(self, ..., favorite_is_active=None, favorite_toggle=None) -> None:
        ...
        self._favorite_is_active = favorite_is_active or (lambda _item: False)
        self._favorite_toggle = favorite_toggle or (lambda _item: None)
        self.favorite_button = self._create_icon_button("favorite.svg", "收藏")
        self.favorite_button.clicked.connect(self._toggle_current_favorite)
        self.detail_actions_layout.addWidget(self.favorite_button)

    def _toggle_current_favorite(self) -> None:
        item = self._current_play_item()
        if item is None:
            return
        self._favorite_toggle(item)
        self._refresh_favorite_button()

    def _refresh_favorite_button(self) -> None:
        item = self._current_play_item()
        active = item is not None and self._favorite_is_active(item)
        self.favorite_button.setVisible(item is not None)
        self.favorite_button.setToolTip("取消收藏" if active else "收藏")
        self._set_button_icon(self.favorite_button, "favorite-filled.svg" if active else "favorite.svg")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_browse_page_ui.py -k "favorite_toggle" -v`

Expected: PASS

Run: `uv run pytest tests/test_player_window_ui.py -k "detail_favorite_icon_button" -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/ui/browse_page.py src/atv_player/ui/player_window.py src/atv_player/models.py tests/test_browse_page_ui.py tests/test_player_window_ui.py
git commit -m "feat: add favorite entry points"
```

## Task 5: Main Window Wiring, Favorites Page Integration, And App Assembly

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/app.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing main-window integration tests**

```python
def test_main_window_registers_favorites_tab_and_header_button(qtbot) -> None:
    window = MainWindow(
        history_controller=FakeStaticController(),
        favorites_controller=FakeFavoritesController(),
        config=AppConfig(),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    assert window.favorites_button.toolTip() == "我的收藏"
    assert window._tab_key_for_widget(window.favorites_page) == "favorites"


def test_main_window_opens_browse_favorite_record(qtbot, monkeypatch) -> None:
    opened = []
    window = MainWindow(
        history_controller=FakeStaticController(),
        favorites_controller=FakeFavoritesController(),
        config=AppConfig(),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_start_open_request", lambda builder: opened.append(builder()) or 1)
    record = FavoriteRecord(
        source_kind="browse",
        source_key="",
        source_name="文件浏览",
        vod_id="detail-1",
        vod_name_snapshot="庆余年",
        latest_vod_name="庆余年",
        vod_pic="",
        vod_remarks="",
        title_changed=False,
        created_at=10,
        updated_at=10,
    )

    window.open_favorite_detail(record)

    assert opened[0].source_kind == "browse"
```

- [ ] **Step 2: Write the failing app assembly test**

```python
def test_app_coordinator_builds_main_window_with_favorites_controller(tmp_path: Path, monkeypatch) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    coordinator = AppCoordinator(repo)
    captured = {}

    class RecordingMainWindow:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("atv_player.app.MainWindow", RecordingMainWindow)
    coordinator.show_main()

    assert captured["favorites_controller"] is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "favorites_tab" -v`

Expected: FAIL with missing `favorites_controller`, `favorites_page`, or `favorites_button`

Run: `uv run pytest tests/test_app.py -k "favorites_controller" -v`

Expected: FAIL with missing constructor wiring

- [ ] **Step 4: Wire favorites repository/controller in app assembly**

```python
from atv_player.controllers.favorites_controller import FavoritesController
from atv_player.favorites_repository import FavoritesRepository

...
if hasattr(repo, "database_path"):
    self._favorites_repository = FavoritesRepository(repo.database_path)
else:
    self._favorites_repository = None

...
favorites_controller = FavoritesController(
    self._favorites_repository,
    detail_loader_by_source={
        "browse": lambda record: self.browse_controller.resolve_folder_play_item(PlayItem(title="", url="", vod_id=record.vod_id)),
        "telegram": lambda record: self.telegram_controller.build_request(record.vod_id).vod,
        "bilibili": lambda record: self.bilibili_controller.build_request(record.vod_id).vod,
        "youtube": lambda record: self.youtube_controller.build_request(record.vod_id).vod,
        "emby": lambda record: self.emby_controller.build_request(record.vod_id).vod,
        "jellyfin": lambda record: self.jellyfin_controller.build_request(record.vod_id).vod,
        "feiniu": lambda record: self.feiniu_controller.build_request(record.vod_id).vod,
    },
)
```

- [ ] **Step 5: Register the page, tab, header button, and favorite-open routing**

```python
self.favorites_page = FavoritesPage(favorites_controller)
...
self._trailing_tab_definitions = [
    _TabDefinition("browse", "文件浏览", self.browse_page),
    _TabDefinition("favorites", "我的收藏", self.favorites_page),
    _TabDefinition("history", "播放记录", self.history_page),
]
...
self.favorites_button = QPushButton("")
self._configure_header_icon_button(self.favorites_button, "我的收藏")
self.header_action_row.insertWidget(1, self.favorites_button)
self.favorites_button.clicked.connect(lambda: self.nav_tabs.setCurrentWidget(self.favorites_page))
...
self.favorites_page.open_detail_requested.connect(self.open_favorite_detail)

def open_favorite_detail(self, record: FavoriteRecord) -> None:
    if record.source_kind == "browse":
        self._start_open_request(lambda: self.browse_controller.build_request_from_detail(record.vod_id))
        return
    if record.source_kind == "spider_plugin":
        controller = self._plugin_controller_by_id(record.source_key)
        if controller is None:
            self.show_error(f"没有可播放的项目: {record.source_name or record.vod_id}")
            return
        self._start_open_request(lambda: controller.build_request(record.vod_id))
        return
    if record.source_kind == "telegram":
        self._start_open_request(lambda: self.telegram_controller.build_request(record.vod_id))
        return
    ...
```

- [ ] **Step 6: Connect browse/player favorite handlers from the main window**

```python
self.browse_page.set_favorite_handlers(
    is_favorited=lambda item: favorites_controller.is_favorited(source_kind="browse", source_key="", vod_id=item.vod_id),
    toggle_favorite=lambda item: self._toggle_browse_favorite(item),
)

def _toggle_browse_favorite(self, item: VodItem) -> None:
    payload = {
        "source_kind": "browse",
        "source_key": "",
        "source_name": "文件浏览",
        "vod_id": item.vod_id,
        "vod_name_snapshot": item.vod_name,
        "latest_vod_name": item.vod_name,
        "vod_pic": item.vod_pic,
        "vod_remarks": item.vod_remarks,
        "title_changed": False,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    if self._favorites_controller.is_favorited(source_kind="browse", source_key="", vod_id=item.vod_id):
        self._favorites_controller.remove_favorite([FavoriteRecord(**payload)])
    else:
        self._favorites_controller.add_favorite(payload)
```

- [ ] **Step 7: Run the focused integration tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "favorites_tab or open_favorite_detail" -v`

Expected: PASS

Run: `uv run pytest tests/test_app.py -k "favorites_controller" -v`

Expected: PASS

- [ ] **Step 8: Run the full favorites-related test set**

Run: `uv run pytest tests/test_favorites_repository.py tests/test_favorites_controller.py tests/test_favorites_page_ui.py tests/test_browse_page_ui.py tests/test_player_window_ui.py tests/test_main_window_ui.py tests/test_app.py -v`

Expected: PASS with all new favorites coverage green

- [ ] **Step 9: Commit**

```bash
git add src/atv_player/app.py src/atv_player/ui/main_window.py tests/test_main_window_ui.py tests/test_app.py
git commit -m "feat: wire favorites feature"
```

## Self-Review

### Spec Coverage

- local SQLite favorites store: covered by Task 1
- `vod_name` snapshot persistence and compare-only-on-`vod_name`: covered by Task 1 and Task 2
- dedicated card-based favorites page: covered by Task 3
- subtle changed-title hint via border/icon: covered by Task 3
- list-page right-click favorite toggle: covered by Task 4
- player detail-area icon toggle: covered by Task 4
- delete selected and clear filtered results: covered by Task 3
- reopen through original source: covered by Task 5
- add header icon button between browse/history: covered by Task 5
- app dependency wiring: covered by Task 5

No spec gaps found.

### Placeholder Scan

- no `TODO`, `TBD`, or “similar to previous task” placeholders left in the plan
- every task includes explicit files, commands, expected results, and code snippets

### Type Consistency

- repository type is `FavoriteRecord`
- controller UI type is `FavoriteCardItem`
- page open signal emits `FavoriteRecord`
- `open_favorite_detail()` in `MainWindow` consumes `FavoriteRecord`
- comparison field is consistently `vod_name_snapshot` vs `latest_vod_name`

No naming mismatches found.
