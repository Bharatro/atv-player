from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from time import time

from atv_player.metadata.query import normalize_metadata_query_inputs
from atv_player.sqlite_utils import managed_connection


def normalize_metadata_binding_title(value: object) -> str:
    text, _year = normalize_metadata_query_inputs(value, "")
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text)
    return compact.casefold()


def normalize_metadata_binding_year(value: object) -> str:
    _title, year = normalize_metadata_query_inputs("", value)
    if year:
        match = re.search(r"(\d{4})", year)
        return match.group(1) if match else year
    text = str(value or "").strip()
    match = re.search(r"(\d{4})", text)
    return match.group(1) if match else ""


def metadata_binding_query_key(title: object, year: object) -> str:
    normalized_title, normalized_year = normalize_metadata_query_inputs(title, year)
    compact_title = re.sub(r"\s+", "", normalized_title).casefold()
    match = re.search(r"(\d{4})", normalized_year)
    compact_year = match.group(1) if match else ""
    return f"{compact_title}\x1f{compact_year}"


def bilibili_season_binding_title(season_id: object) -> str:
    text = str(season_id or "").strip()
    return f"bilibili:season:{text}" if text.isdigit() else ""


# 特殊 provider 标记：行不是元数据绑定，而是"查询重定向"——用户在刮削对话框点
# "自动刮削"时手动修正过查询标题，重开会话后自动水合按原始标题查不到，需要先
# 重定向到修正后的标题再搜索。
QUERY_REDIRECT_PROVIDER = "__query_redirect__"


def is_query_redirect_binding(binding: MetadataBinding | None) -> bool:
    if binding is None:
        return False
    return str(binding.provider or "") == QUERY_REDIRECT_PROVIDER


@dataclass(slots=True)
class MetadataBinding:
    normalized_title: str
    normalized_year: str
    provider: str
    provider_id: str
    matched_title: str = ""
    matched_year: str = ""
    updated_at: int = 0


class MetadataBindingRepository:
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
                CREATE TABLE IF NOT EXISTS metadata_bindings (
                    query_key TEXT PRIMARY KEY,
                    normalized_title TEXT NOT NULL,
                    normalized_year TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    matched_title TEXT NOT NULL DEFAULT '',
                    matched_year TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def load(self, title: object, year: object) -> MetadataBinding | None:
        query_key = metadata_binding_query_key(title, year)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT normalized_title, normalized_year, provider, provider_id, matched_title, matched_year, updated_at
                FROM metadata_bindings
                WHERE query_key = ?
                """,
                (query_key,),
            ).fetchone()
        if row is None:
            return None
        return MetadataBinding(*row)

    def load_by_title(self, title: object) -> MetadataBinding | None:
        normalized_title = normalize_metadata_binding_title(title)
        if not normalized_title:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT normalized_title, normalized_year, provider, provider_id, matched_title, matched_year, updated_at
                FROM metadata_bindings
                WHERE normalized_title = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (normalized_title,),
            ).fetchone()
        if row is None:
            return None
        return MetadataBinding(*row)

    def save_query_redirect(self, title: object, year: object, redirect_title: object, redirect_year: object = "") -> None:
        normalized_redirect = str(redirect_title or "").strip()
        if not normalized_redirect:
            return
        self.save(
            title,
            year,
            provider=QUERY_REDIRECT_PROVIDER,
            provider_id=normalized_redirect,
            matched_title=normalized_redirect,
            matched_year=redirect_year,
        )

    def load_query_redirect(self, title: object, year: object) -> tuple[str, str] | None:
        binding = self.load(title, year)
        if not is_query_redirect_binding(binding):
            return None
        redirect_title = str(binding.provider_id or "").strip()
        if not redirect_title:
            return None
        return redirect_title, str(binding.matched_year or "").strip()

    def save(
        self,
        title: object,
        year: object,
        *,
        provider: str,
        provider_id: str,
        matched_title: str = "",
        matched_year: str = "",
    ) -> None:
        normalized_title = normalize_metadata_binding_title(title)
        normalized_year = normalize_metadata_binding_year(year)
        query_key = metadata_binding_query_key(title, year)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO metadata_bindings (
                    query_key, normalized_title, normalized_year, provider, provider_id, matched_title, matched_year, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(query_key) DO UPDATE SET
                    provider = excluded.provider,
                    provider_id = excluded.provider_id,
                    matched_title = excluded.matched_title,
                    matched_year = excluded.matched_year,
                    updated_at = excluded.updated_at
                """,
                (
                    query_key,
                    normalized_title,
                    normalized_year,
                    str(provider or "").strip(),
                    str(provider_id or "").strip(),
                    str(matched_title or "").strip(),
                    str(matched_year or "").strip(),
                    int(time()),
                ),
            )

    def delete(self, title: object, year: object) -> None:
        query_key = metadata_binding_query_key(title, year)
        with self._connect() as conn:
            conn.execute("DELETE FROM metadata_bindings WHERE query_key = ?", (query_key,))
