from __future__ import annotations

from collections.abc import Iterable
import re

import httpx

from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


class IqiyiMetadataProvider:
    name = "iqiyi"
    _SEARCH_URL = "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
    _SEARCH_HEADERS = {"user-agent": "Mozilla/5.0", "referer": "https://www.iqiyi.com/"}
    _ALLOWED_TEMPLATES = {101, 102, 103, 112}
    _NON_NATIVE_SITE_PENALTY = 0.35

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
                "key": title,
                "pageNum": 1,
                "pageSize": 25,
                "mode": 1,
                "current_page": 1,
            },
            headers=dict(self._SEARCH_HEADERS),
            follow_redirects=True,
            timeout=10.0,
        )
        payload = response.json()
        matches: list[MetadataMatch] = []
        for album_info in self._iter_album_infos(payload):
            provider_id = self._provider_id(album_info)
            match_title = str(album_info.get("title") or "").strip()
            if not provider_id or not match_title:
                continue
            match = MetadataMatch(
                provider=self.name,
                provider_id=provider_id,
                title=match_title,
                year=self._year_value(album_info),
                raw=dict(album_info),
            )
            match.score = score_match(candidate, match)
            match.score = self._apply_native_site_penalty(match)
            matches.append(match)
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = dict(match.raw)
        detail_fields: list[dict[str, object]] = []
        page_url = str(match.provider_id or payload.get("pageUrl") or "").strip()
        if page_url.startswith(("http://", "https://")):
            detail_fields.append({"label": "播放链接", "value": page_url})
        detail_fields.extend(self._site_metric_fields(payload))
        for key in ("releaseTime", "updateTime", "timeLength"):
            item = payload.get(key)
            if not isinstance(item, dict):
                continue
            label = str(item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
            if key == "updateTime" and value:
                label = "更新时间"
            if label and value:
                detail_fields.append({"label": label, "value": value})
        return MetadataRecord(
            provider=self.name,
            provider_id=str(match.provider_id or "").strip(),
            title=str(payload.get("title") or match.title or "").strip(),
            year=self._year_value(payload) or str(match.year or "").strip(),
            overview=self._overview_value(payload),
            actors=self._people_titles((payload.get("actors") or {}).get("value")),
            directors=self._people_titles((payload.get("directors") or {}).get("value")),
            genres=self._genres(payload),
            country=self._nested_value(payload.get("region")),
            language=self._nested_value(payload.get("language")),
            detail_fields=detail_fields,
        )

    def _apply_native_site_penalty(self, match: MetadataMatch) -> float:
        site_name = str(match.raw.get("siteName") or "").strip()
        if site_name and site_name != "爱奇艺":
            return max(0.0, float(match.score or 0.0) - self._NON_NATIVE_SITE_PENALTY)
        return float(match.score or 0.0)

    def _iter_album_infos(self, payload: dict) -> Iterable[dict]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        templates = data.get("templates")
        if not isinstance(templates, list):
            return []
        album_infos: list[dict] = []
        for template in templates:
            if not isinstance(template, dict):
                continue
            template_id = int(template.get("template") or 0)
            if template_id not in self._ALLOWED_TEMPLATES:
                continue
            album_info = template.get("albumInfo")
            if isinstance(album_info, dict):
                album_infos.append(self._merge_search_episode_rows(album_info, template.get("videoinfos")))
            intent_album_infos = template.get("intentAlbumInfos")
            if isinstance(intent_album_infos, list):
                album_infos.extend(
                    self._merge_search_episode_rows(item, item.get("videoinfos"))
                    for item in intent_album_infos
                    if isinstance(item, dict)
                )
        return album_infos

    def _merge_search_episode_rows(self, album_info: dict, fallback_videoinfos: object) -> dict:
        merged = dict(album_info)
        existing_videos = merged.get("videos")
        if isinstance(existing_videos, list) and existing_videos:
            return merged
        videoinfos = merged.get("videoinfos")
        if isinstance(videoinfos, list) and videoinfos:
            merged["videos"] = list(videoinfos)
            return merged
        if isinstance(fallback_videoinfos, list) and fallback_videoinfos:
            merged["videos"] = list(fallback_videoinfos)
        return merged

    def _provider_id(self, payload: dict) -> str:
        page_url = str(payload.get("pageUrl") or "").strip()
        if page_url:
            return page_url
        qipu_id = str(payload.get("qipuId") or payload.get("playQipuId") or "").strip()
        if qipu_id:
            return f"qipu:{qipu_id}"
        return str(payload.get("title") or "").strip()

    def _year_value(self, payload: dict) -> str:
        year = self._nested_value(payload.get("year"))
        if year:
            return year
        for key in ("subtitle", "superscript"):
            value = str(payload.get(key) or "").strip()
            if value.isdigit() and len(value) == 4:
                return value
        return ""

    def _overview_value(self, payload: dict) -> str:
        for value in (
            self._nested_value(payload.get("brief")),
            str(payload.get("introduction") or "").strip(),
            str(payload.get("promptDesc") or "").strip(),
        ):
            if value:
                return re.sub(r"\s+", " ", value).strip()
        return ""

    def _people_titles(self, values: object) -> list[str]:
        people: list[str] = []
        for item in values or []:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
            else:
                title = str(item or "").strip()
            if title:
                people.append(title)
        return people

    def _genres(self, payload: dict) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        channel = payload.get("channel")
        if not payload.get("baseTags") and not payload.get("category"):
            channel_value = str(channel or "").strip()
            channel_name = channel_value.split(",", 1)[0].strip()
            if channel_name and channel_name not in seen:
                ordered.append(channel_name)
                seen.add(channel_name)

        for value in payload.get("baseTags") or []:
            genre = str((value or {}).get("value") or "").strip() if isinstance(value, dict) else str(value or "").strip()
            if genre and genre not in seen:
                ordered.append(genre)
                seen.add(genre)
        category = payload.get("category")
        category_value = str(category.get("value") or "").strip() if isinstance(category, dict) else ""
        for genre in re.split(r"[,/]", category_value):
            normalized = genre.strip()
            if normalized and normalized not in seen:
                ordered.append(normalized)
                seen.add(normalized)
        if not payload.get("baseTags"):
            for item in payload.get("metaTags") or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("style") or "").strip().lower() == "special":
                    continue
                normalized = str(item.get("name") or "").strip()
                if normalized and normalized not in seen:
                    ordered.append(normalized)
                    seen.add(normalized)
        return ordered

    def _nested_value(self, payload: object) -> str:
        if isinstance(payload, dict):
            return str(payload.get("value") or "").strip()
        return str(payload or "").strip()

    def _site_metric_fields(self, payload: dict) -> list[dict[str, str]]:
        fields: list[dict[str, str]] = []
        for label, keys in (
            ("站内评分", ("siteScore", "score", "rating")),
            ("热度", ("heat", "hot", "popularity")),
            ("评论", ("commentCount", "comments", "comment")),
        ):
            value = self._metric_value(payload, keys)
            if value:
                fields.append({"label": label, "value": value})
        return fields

    def _metric_value(self, payload: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                text = str(value.get("value") or value.get("score") or value.get("text") or "").strip()
            else:
                text = str(value or "").strip()
            if text:
                return text
        return ""
