from __future__ import annotations

import httpx

from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


class MiguMetadataProvider:
    name = "migu"
    _SEARCH_URL = "https://jadeite.migu.cn/search/v3/open-search"

    def __init__(self, post=httpx.post) -> None:
        self._post = post

    def can_enrich(self, _context) -> bool:
        return True

    def search_cache_key(self, candidate: MetadataQuery) -> tuple[str, str]:
        return str(candidate.title or "").strip(), str(candidate.year or "").strip()

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        title = str(candidate.title or "").strip()
        if not title:
            return []
        response = self._post(
            self._SEARCH_URL,
            json={
                "appVersion": "6.1.1.00",
                "ct": 101,
                "isCorrectWord": 1,
                "k": title,
                "mediaSource": 9000000,
                "pageIdx": 1,
                "pageSize": 20,
                "copyrightTerminal": 3,
                "searchScene": 2,
                "uiVersion": "A3.26.0",
            },
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/144.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://www.miguvideo.com",
                "Referer": "https://www.miguvideo.com/",
                "appId": "miguvideo",
                "terminalId": "www",
            },
            timeout=10.0,
            follow_redirects=True,
        )
        payload = response.json()
        rows = ((payload.get("body") or {}).get("contentInfoList") or [])
        if not isinstance(rows, list):
            return []
        matches: list[MetadataMatch] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            asset = row.get("shortMediaAsset")
            if not isinstance(asset, dict) or not asset.get("isLong"):
                continue
            normalized = self._normalize_asset(asset)
            provider_id = str(normalized.get("provider_id") or "").strip()
            match_title = str(normalized.get("title") or "").strip()
            if not provider_id or not match_title or provider_id in seen:
                continue
            seen.add(provider_id)
            match = MetadataMatch(
                provider=self.name,
                provider_id=provider_id,
                title=match_title,
                year=str(normalized.get("year") or "").strip(),
                raw=normalized,
            )
            match.score = score_match(candidate, match)
            matches.append(match)
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = dict(match.raw or {})
        detail_fields: list[dict[str, object]] = []
        type_name = str(payload.get("type") or "").strip()
        if type_name:
            detail_fields.append({"label": "类型", "value": type_name})
        provider_id = str(match.provider_id or "").strip()
        if provider_id:
            detail_fields.append(
                {"label": "播放链接", "value": f"https://www.miguvideo.com/p/detail/{provider_id}"}
            )
        return MetadataRecord(
            provider=self.name,
            provider_id=str(match.provider_id or "").strip(),
            title=str(payload.get("title") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            poster=str(payload.get("poster") or "").strip(),
            genres=[type_name] if type_name else [],
            detail_fields=detail_fields,
        )

    def _normalize_asset(self, asset: dict[str, object]) -> dict[str, object]:
        provider_id = self._provider_id(asset)
        return {
            "title": str(asset.get("name") or "").strip(),
            "provider_id": provider_id,
            "year": str(asset.get("year") or "").strip(),
            "poster": self._poster(asset),
            "type": str(asset.get("contDisplayName") or "").strip(),
        }

    def _provider_id(self, asset: dict[str, object]) -> str:
        extra_data = asset.get("extraData")
        if isinstance(extra_data, dict):
            episodes = extra_data.get("episodes")
            if isinstance(episodes, list) and episodes:
                return str(episodes[0] or "").strip()
        return str(asset.get("pID") or "").strip()

    def _poster(self, asset: dict[str, object]) -> str:
        pics = asset.get("h5pics")
        if not isinstance(pics, dict):
            return ""
        for key in ("highResolutionV", "highResolutionH", "imgH", "imgV"):
            value = str(pics.get(key) or "").strip()
            if value:
                return value
        return ""
