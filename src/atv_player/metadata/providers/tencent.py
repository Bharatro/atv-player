from __future__ import annotations

import uuid

import httpx

from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


class TencentMetadataProvider:
    name = "tencent"
    _SEARCH_URL = "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch"
    _SEARCH_PARAMS = {"vversion_platform": "2"}
    _SEARCH_HEADERS = {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": "https://v.qq.com",
        "referer": "https://v.qq.com/",
        "trpc-trans-info": '{"trpc-env":""}',
        "user-agent": "Mozilla/5.0",
    }
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
            matches.append(match)
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = dict(match.raw)
        site_name = str(payload.get("site_name") or "").strip()
        detail_fields = [{"label": "来源站点", "value": site_name}] if site_name else []
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
            detail_fields=detail_fields,
        )

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
        normal_list = data.get("normalList")
        if not isinstance(normal_list, dict):
            return []
        item_list = normal_list.get("itemList")
        if not isinstance(item_list, list):
            return []
        return [
            item
            for item in item_list
            if isinstance(item, dict)
            if isinstance(item.get("doc"), dict)
            if int((item.get("doc") or {}).get("dataType") or 0) == 2
            if isinstance(item.get("videoInfo"), dict)
        ]

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
            "genres": self._genres(video_info),
            "site_name": self._site_name(video_info),
            "provider_id": self._provider_id(video_info, doc),
        }

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
            return str(year)
        value = str(year or "").strip()
        return value if value.isdigit() and len(value) == 4 else ""

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

        add(payload.get("typeName"))
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
