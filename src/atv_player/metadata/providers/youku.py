from __future__ import annotations

import math
import re
from urllib.parse import parse_qs, urlparse

import httpx

from atv_player.danmaku.utils import strip_episode_suffix
from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


class YoukuMetadataProvider:
    name = "youku"
    _SEARCH_URL = "https://search.youku.com/api/search"
    _SEARCH_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    def __init__(self, get=httpx.get) -> None:
        self._get = get

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        title = str(candidate.title or "").strip()
        if not title:
            return []
        response = self._get(
            self._SEARCH_URL,
            params={
                "keyword": title,
                "userAgent": self._SEARCH_USER_AGENT,
                "site": 1,
                "categories": 0,
                "ftype": 0,
                "ob": 0,
                "pg": 1,
            },
            headers={
                "user-agent": self._SEARCH_USER_AGENT,
                "accept": "application/json",
                "referer": "https://www.youku.com/",
            },
            follow_redirects=True,
            timeout=10.0,
        )
        payload = response.json()
        matches: list[MetadataMatch] = []
        seen: set[str] = set()
        for item in self._iter_search_items(payload):
            provider_id = str(item.get("provider_id") or "").strip()
            match_title = str(item.get("title") or "").strip()
            if not provider_id or not match_title or provider_id in seen:
                continue
            seen.add(provider_id)
            match = MetadataMatch(
                provider=self.name,
                provider_id=provider_id,
                title=match_title,
                year=str(item.get("year") or "").strip(),
                raw=dict(item),
            )
            match.score = score_match(candidate, match)
            matches.append(match)
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = dict(match.raw or {})
        page_url = str(match.provider_id or payload.get("provider_id") or "").strip()
        detail_fields: list[dict[str, object]] = []
        if page_url:
            detail_fields.append({"label": "播放链接", "value": page_url})
        return MetadataRecord(
            provider=self.name,
            provider_id=page_url,
            title=str(payload.get("title") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            overview=str(payload.get("overview") or "").strip(),
            genres=list(payload.get("genres") or []),
            detail_fields=detail_fields,
        )

    def _iter_search_items(self, payload: dict) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        page_components = payload.get("pageComponentList")
        if isinstance(page_components, list):
            items.extend(self._items_from_page_components(page_components))
        series_list = payload.get("serisesList")
        if isinstance(series_list, list):
            items.extend(self._items_from_series_list(series_list))
        return items

    def _items_from_page_components(self, components: list[object]) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for component in components:
            if not isinstance(component, dict):
                continue
            common = component.get("commonData") if isinstance(component.get("commonData"), dict) else {}
            if not self._is_youku_common_data(common):
                continue
            episodes = self._component_episode_items(component)
            page_url = self._component_primary_url(common) or (str(episodes[0].get("url") or "") if episodes else "")
            title = self._series_title(common, episodes)
            if not title or not page_url:
                continue
            results.append(
                {
                    "title": title,
                    "provider_id": page_url,
                    "episodes": episodes,
                    "category": "优酷",
                }
            )
        return results

    def _items_from_series_list(self, series_list: list[object]) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for item in series_list:
            if not isinstance(item, dict):
                continue
            url = self._series_item_url(item)
            title = strip_episode_suffix(str(item.get("title") or item.get("displayName") or "").strip())
            if title and url:
                results.append(
                    {
                        "title": title,
                        "provider_id": url,
                        "episodes": [{"title": item.get("title"), "url": url}],
                        "category": "优酷",
                    }
                )
        return results

    def _is_youku_common_data(self, common: dict) -> bool:
        if int(common.get("isYouku") or 0) == 1 or int(common.get("hasYouku") or 0) == 1:
            return True
        for candidate in (
            common.get("videoLink"),
            ((common.get("leftButtonDTO") or {}).get("action") or {}).get("value"),
            common.get("action", {}).get("value") if isinstance(common.get("action"), dict) else "",
        ):
            if "youku.com" in str(candidate or ""):
                return True
        return False

    def _component_episode_items(self, component: dict) -> list[dict[str, object]]:
        component_map = component.get("componentMap") if isinstance(component.get("componentMap"), dict) else {}
        episodes = (component_map.get("1035") or {}).get("data") if isinstance(component_map.get("1035"), dict) else []
        if not isinstance(episodes, list):
            return []
        output: list[dict[str, object]] = []
        for episode in episodes:
            if not isinstance(episode, dict):
                continue
            title = str(episode.get("title") or "").strip()
            url = self._component_episode_url(episode)
            if title and url:
                output.append(
                    {
                        "episode_number": self._episode_number(title),
                        "title": title,
                        "url": url,
                        "duration_seconds": self._to_duration_seconds(episode.get("duration")),
                    }
                )
        return output

    def _series_title(self, common: dict, episodes: list[dict[str, object]]) -> str:
        title = str((common.get("titleDTO") or {}).get("displayName") or "").strip()
        if title:
            return strip_episode_suffix(title)
        for episode in episodes:
            title = strip_episode_suffix(str(episode.get("title") or "").strip())
            if title:
                return title
        return ""

    def _component_primary_url(self, common: dict) -> str:
        for candidate in (
            common.get("videoLink"),
            ((common.get("leftButtonDTO") or {}).get("action") or {}).get("value"),
            common.get("action", {}).get("value") if isinstance(common.get("action"), dict) else "",
        ):
            url = self._normalize_youku_url(str(candidate or "").strip())
            if url:
                return url
        return ""

    def _component_episode_url(self, episode: dict) -> str:
        video_id = str(episode.get("videoId") or "").strip()
        if video_id:
            return f"https://v.youku.com/v_show/id_{video_id}.html"
        action = episode.get("action") if isinstance(episode.get("action"), dict) else {}
        return self._normalize_youku_url(str(action.get("value") or "").strip())

    def _series_item_url(self, item: dict) -> str:
        video_id = str(item.get("videoId") or "").strip()
        if video_id:
            return f"https://v.youku.com/v_show/id_{video_id}.html"
        action = item.get("action") if isinstance(item.get("action"), dict) else {}
        return self._normalize_youku_url(str(action.get("value") or "").strip())

    def _normalize_youku_url(self, value: str) -> str:
        candidate = str(value or "").strip()
        if not candidate:
            return ""
        if candidate.startswith("//"):
            candidate = f"https:{candidate}"
        if candidate.startswith("https://v.youku.com/v_show/"):
            return candidate
        parsed = urlparse(candidate)
        vid = parse_qs(parsed.query).get("vid", [""])[0].strip()
        if vid:
            return f"https://v.youku.com/v_show/id_{vid}.html"
        return ""

    def _episode_number(self, title: object) -> int:
        match = re.search(r"(?:第\s*)?0*(\d{1,4})\s*(?:集|话|期)?\s*$", str(title or "").strip())
        if match is None:
            return 0
        return int(match.group(1))

    def _to_duration_seconds(self, value: object) -> int:
        try:
            return max(0, int(math.ceil(float(value or 0))))
        except (TypeError, ValueError):
            return 0
