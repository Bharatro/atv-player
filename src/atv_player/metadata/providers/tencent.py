from __future__ import annotations

import logging
import re
import uuid
from dataclasses import replace

import httpx

from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord

logger = logging.getLogger(__name__)


class TencentMetadataProvider:
    name = "tencent"
    _SEARCH_CACHE_VERSION = "area-box-v3"
    _SEARCH_URL = "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch"
    _SEARCH_PARAMS = {"vversion_platform": "2"}
    _NON_NATIVE_SITE_PENALTY = 0.35
    _SEARCH_HEADERS = {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": "https://v.qq.com",
        "referer": "https://v.qq.com/",
        "trpc-trans-info": '{"trpc-env":""}',
        "user-agent": "Mozilla/5.0",
    }
    # Official per-cover episode list (variety shows live here, keyed by publish date).
    _EPISODE_LIST_URL = (
        "https://pbaccess.video.qq.com/trpc.universal_backend_service.page_server_rpc.PageServer/GetPageData"
    )
    _EPISODE_LIST_PARAMS = {"video_appid": "3000010", "vplatform": "2", "vversion_name": "8.2.96"}
    _EPISODE_LIST_HEADERS = {
        "content-type": "application/json",
        "origin": "https://v.qq.com",
        "referer": "https://v.qq.com/",
        "user-agent": "Mozilla/5.0",
    }
    _COVER_ID_RE = re.compile(r"/cover/([A-Za-z0-9]+)")
    _FEATURE_LIST = [
        "DEFAULT_FEFEATURE",
        "PC_SHORT_VIDEOS_WATERFALL",
        "PC_WANT_EPISODE_V2",
        "PC_WANT_EPISODE",
    ]

    def __init__(self, post=httpx.post) -> None:
        self._post = post

    def can_enrich(self, _context) -> bool:
        return True

    def search_cache_key(self, candidate: MetadataQuery) -> tuple[str, str]:
        return str(candidate.title or "").strip(), f"{str(candidate.year or '').strip()}#{self._SEARCH_CACHE_VERSION}"

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        title = str(candidate.title or "").strip()
        if not title:
            return []
        response = self._post(
            self._SEARCH_URL,
            params=dict(self._SEARCH_PARAMS),
            headers=dict(self._SEARCH_HEADERS),
            json=self._build_search_payload(title),
            follow_redirects=True,
            timeout=10.0,
        )
        payload = response.json()
        matches: list[MetadataMatch] = []
        for item in self._iter_video_items(payload):
            normalized = self._normalize_item(item)
            provider_id = str(normalized.get("provider_id") or "").strip()
            match_title = str(normalized.get("title") or "").strip()
            if not provider_id or not match_title:
                continue
            match = MetadataMatch(
                provider=self.name,
                provider_id=provider_id,
                title=match_title,
                year=str(normalized.get("year") or "").strip(),
                raw=normalized,
            )
            match.score = score_match(candidate, match)
            match.score = self._apply_native_site_penalty(match)
            matches.append(match)
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = dict(match.raw)
        return MetadataRecord(
            provider=self.name,
            provider_id=str(match.provider_id or "").strip(),
            title=str(payload.get("title") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            overview=str(payload.get("overview") or "").strip(),
            actors=list(payload.get("actors") or []),
            directors=list(payload.get("directors") or []),
            genres=list(payload.get("genres") or []),
            country=str(payload.get("country") or "").strip(),
            language=str(payload.get("language") or "").strip(),
            detail_fields=self._detail_fields(payload, match),
        )

    def _apply_native_site_penalty(self, match: MetadataMatch) -> float:
        site_name = str(match.raw.get("site_name") or "").strip()
        if site_name and site_name != "腾讯视频":
            return max(0.0, float(match.score or 0.0) - self._NON_NATIVE_SITE_PENALTY)
        return float(match.score or 0.0)

    def _hydrate_episode_candidate(self, candidate: MetadataMatch) -> MetadataMatch:
        """Fetch the cover's full episode list (titles + publish dates).

        Search results only carry a few preview episodes; the official per-cover
        list is what variety-show rewriting needs to align files by air date.
        Enriches ``candidate.raw`` with ``episodes=[{"title","publish_date"}, ...]``.
        """
        provider_id = str(getattr(candidate, "provider_id", "") or "")
        cover_id = self._cover_id_from_provider_id(provider_id)
        if not cover_id:
            logger.info(
                "Tencent cover episode list skipped: no cover id in provider_id=%s",
                provider_id,
                extra={"log_category": "metadata", "log_source": "app"},
            )
            return candidate
        episodes = self._fetch_cover_episodes(cover_id)
        if not episodes:
            logger.info(
                "Tencent cover episode list empty for cover_id=%s",
                cover_id,
                extra={"log_category": "metadata", "log_source": "app"},
            )
            return candidate
        logger.info(
            "Tencent cover episode list fetched cover_id=%s count=%s",
            cover_id,
            len(episodes),
            extra={"log_category": "metadata", "log_source": "app"},
        )
        raw = dict(getattr(candidate, "raw", {}) or {})
        raw["episodes"] = episodes
        raw["episode_list_source"] = "tencent_cover"
        return replace(candidate, raw=raw)

    def _cover_id_from_provider_id(self, provider_id: str) -> str:
        match = self._COVER_ID_RE.search(str(provider_id or ""))
        return match.group(1) if match else ""

    def _fetch_cover_episodes(self, cover_id: str) -> list[dict]:
        if not cover_id:
            return []
        payload = {
            "page_params": {
                "req_from": "web_vsite",
                "page_id": "vsite_episode_list",
                "page_type": "detail_operation",
                "id_type": "1",
                "page_size": "100",
                "cid": cover_id,
                "req_from_platform_id": "2",
                "is_skp_style": "false",
            },
            "has_cache": 1,
        }
        try:
            response = self._post(
                self._EPISODE_LIST_URL,
                params=dict(self._EPISODE_LIST_PARAMS),
                headers=dict(self._EPISODE_LIST_HEADERS),
                json=payload,
                follow_redirects=True,
                timeout=10.0,
            )
            data = response.json()
        except Exception as exc:
            logger.info(
                "Tencent cover episode list fetch failed cover_id=%s error=%s",
                cover_id,
                exc,
                extra={"log_category": "metadata", "log_source": "app"},
            )
            return []
        return self._parse_cover_episodes(data)

    def _parse_cover_episodes(self, payload: object) -> list[dict]:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return []
        module_list_datas = data.get("module_list_datas")
        if not isinstance(module_list_datas, list):
            return []
        episodes: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for module in module_list_datas:
            if not isinstance(module, dict):
                continue
            for module_data in module.get("module_datas") or []:
                item_data_lists = module_data.get("item_data_lists") if isinstance(module_data, dict) else None
                if not isinstance(item_data_lists, dict):
                    continue
                for item in item_data_lists.get("item_datas") or []:
                    params = item.get("item_params") if isinstance(item, dict) else None
                    if not isinstance(params, dict):
                        continue
                    title = str(
                        params.get("union_title") or params.get("play_title") or params.get("title") or ""
                    ).strip()
                    publish_date = str(params.get("publish_date") or "").strip()
                    # Skip section tabs (第1季/纯享/陪看/花絮…) which carry no publish date.
                    if not title or not publish_date:
                        continue
                    key = (title, publish_date[:10])
                    if key in seen:
                        continue
                    seen.add(key)
                    episodes.append({"title": title, "publish_date": publish_date})
        return episodes

    def _build_search_payload(self, title: str) -> dict[str, object]:
        return {
            "version": "26022601",
            "clientType": 1,
            "filterValue": "",
            "uuid": str(uuid.uuid4()).upper(),
            "retry": 0,
            "query": title,
            "pagenum": 0,
            "isPrefetch": True,
            "pagesize": 30,
            "queryFrom": 0,
            "searchDatakey": "",
            "transInfo": "",
            "isneedQc": True,
            "preQid": "",
            "adClientInfo": "",
            "extraInfo": {
                "isNewMarkLabel": "1",
                "multi_terminal_pc": "1",
                "themeType": "1",
                "sugRelatedIds": "{}",
                "appVersion": "",
                "frontVersion": "26041606",
            },
            "featureList": list(self._FEATURE_LIST),
        }

    def _iter_video_items(self, payload: dict) -> list[dict]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        items: list[dict] = []
        normal_list = data.get("normalList")
        if isinstance(normal_list, dict):
            item_list = normal_list.get("itemList")
            if isinstance(item_list, list):
                items.extend(item for item in item_list if isinstance(item, dict))
        area_box_list = data.get("areaBoxList")
        if isinstance(area_box_list, list):
            for box in area_box_list:
                if not isinstance(box, dict):
                    continue
                item_list = box.get("itemList")
                if not isinstance(item_list, list):
                    continue
                items.extend(item for item in item_list if isinstance(item, dict))
        return [item for item in items if self._is_video_item(item)]

    def _is_video_item(self, item: dict) -> bool:
        doc = item.get("doc")
        if not isinstance(doc, dict):
            return False
        if int(doc.get("dataType") or 0) != 2:
            return False
        return isinstance(item.get("videoInfo"), dict)

    def _normalize_item(self, item: dict) -> dict[str, object]:
        doc = item.get("doc") if isinstance(item.get("doc"), dict) else {}
        video_info = item.get("videoInfo") if isinstance(item.get("videoInfo"), dict) else {}
        return {
            "title": str(video_info.get("title") or "").strip(),
            "year": self._year_value(video_info),
            "overview": str(video_info.get("descrip") or "").strip(),
            "country": str(video_info.get("area") or "").strip(),
            "language": self._language_value(video_info.get("language")),
            "directors": self._string_list(video_info.get("directors")),
            "actors": self._string_list(video_info.get("actors")),
            "typeName": str(video_info.get("typeName") or "").strip(),
            "genres": self._genres(video_info),
            "site_name": self._site_name(video_info),
            "episode_sites": self._episode_sites(video_info),
            "play_sites": self._play_sites(video_info),
            "provider_id": self._provider_id(video_info, doc),
            "siteScore": video_info.get("siteScore"),
            "score": video_info.get("score"),
            "rating": video_info.get("rating"),
            "extraFields": video_info.get("extraFields"),
            "heat": video_info.get("heat"),
            "hot": video_info.get("hot"),
            "popularity": video_info.get("popularity"),
            "commentCount": video_info.get("commentCount"),
            "comments": video_info.get("comments"),
            "comment": video_info.get("comment"),
        }

    def _detail_fields(self, payload: dict, match: MetadataMatch) -> list[dict[str, str]]:
        fields: list[dict[str, str]] = []
        url = str(payload.get("provider_id") or match.provider_id or "").strip()
        if url:
            fields.append({"label": "播放链接", "value": url})
        fields.extend(self._site_metric_fields(payload))
        return fields

    def _site_metric_fields(self, payload: dict) -> list[dict[str, str]]:
        video_info = payload.get("videoInfo") if isinstance(payload.get("videoInfo"), dict) else payload
        fields: list[dict[str, str]] = []
        for label, keys in (
            ("站内评分", ("siteScore", "score", "rating", "extraFields.score")),
            ("热度", ("heat", "hot", "popularity")),
            ("评论", ("commentCount", "comments", "comment")),
        ):
            value = self._metric_value(video_info, keys)
            if value:
                fields.append({"label": label, "value": value})
        return fields

    def _metric_value(self, payload: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            if "." in key:
                head, tail = key.split(".", 1)
                value = payload.get(head)
                if isinstance(value, dict):
                    nested = value.get(tail)
                    text = str(nested or "").strip()
                else:
                    text = ""
            else:
                value = payload.get(key)
                if isinstance(value, dict):
                    text = str(value.get("value") or value.get("score") or value.get("text") or "").strip()
                else:
                    text = str(value or "").strip()
            if text:
                return text
        return ""

    def _episode_sites(self, video_info: dict) -> list[dict]:
        return self._site_list(video_info.get("episodeSites"))

    def _play_sites(self, video_info: dict) -> list[dict]:
        return self._site_list(video_info.get("playSites"))

    def _site_list(self, payload: object) -> list[dict]:
        if not isinstance(payload, list):
            return []
        return [dict(site) for site in payload if isinstance(site, dict)]

    def _provider_id(self, video_info: dict, doc: dict) -> str:
        for site_key in ("playSites", "episodeSites"):
            sites = video_info.get(site_key)
            if not isinstance(sites, list):
                continue
            for site in sites:
                if not isinstance(site, dict):
                    continue
                episodes = site.get("episodeInfoList")
                if not isinstance(episodes, list):
                    continue
                for episode in episodes:
                    if not isinstance(episode, dict):
                        continue
                    url = str(episode.get("url") or "").strip()
                    if url:
                        return url
        cover_id = str(doc.get("id") or "").strip()
        if cover_id:
            return f"https://v.qq.com/x/cover/{cover_id}.html"
        return ""

    def _site_name(self, video_info: dict) -> str:
        for site_key in ("playSites", "episodeSites"):
            sites = video_info.get(site_key)
            if not isinstance(sites, list):
                continue
            for site in sites:
                if not isinstance(site, dict):
                    continue
                site_name = str(site.get("showName") or "").strip()
                if site_name:
                    return site_name
        return "腾讯视频"

    def _year_value(self, payload: dict) -> str:
        year = payload.get("year")
        if isinstance(year, int):
            return str(year) if 1000 <= year <= 9999 else ""
        value = str(year or "").strip()
        return value if value.isdigit() and len(value) == 4 and value != "0000" else ""

    def _language_value(self, payload: object) -> str:
        if isinstance(payload, list):
            values = [str(item or "").strip() for item in payload if str(item or "").strip()]
            return " / ".join(values)
        return str(payload or "").strip()

    def _string_list(self, payload: object) -> list[str]:
        if not isinstance(payload, list):
            return []
        return [text for text in (str(item or "").strip() for item in payload) if text]

    def _genres(self, payload: dict) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add(value: object) -> None:
            text = str(value or "").strip()
            if not text or text in seen:
                return
            ordered.append(text)
            seen.add(text)

        for tag in payload.get("tags") or []:
            if isinstance(tag, dict):
                add(tag.get("text") or tag.get("value") or tag.get("name"))
            else:
                add(tag)
        for tag in payload.get("richTags") or []:
            if not isinstance(tag, dict):
                continue
            if int(tag.get("uiType") or 0) != 1:
                continue
            add(tag.get("text"))
        return ordered
