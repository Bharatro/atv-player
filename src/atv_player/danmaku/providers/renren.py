from __future__ import annotations

import hashlib
import random
import re
import time
from collections.abc import Callable
from urllib.parse import unquote, urlencode, urlparse

import httpx

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.utils import extract_episode_number, should_filter_name

_TV_SECRET_KEY = "cf65GPholnICgyw1xbrpA79XVkizOdMq"
_TV_HOST = "api.gorafie.com"
_MAC_HOST = "api.cluuid.cn"
_WIN_HOST = "api.pleasfun.com"
_TV_DANMU_HOST = "static-dm.qwdjapp.com"
_MAC_DANMU_HOST = "static-dm.lequkeji.com"
_WEB_DANMU_HOST = "static-dm.rrmj.plus"
_TV_USER_AGENT = "okhttp/3.12.13"
_MAC_USER_AGENT = (
    "%E4%BA%BA%E4%BA%BA%E8%A7%86%E9%A2%91%20for%20Mac/1.0 "
    "CFNetwork/3860.600.21 Darwin/25.5.0"
)
_WIN_USER_AGENT = "Boost.Beast/351"
_STATIC_HOSTS = {_TV_DANMU_HOST, _MAC_DANMU_HOST, _WEB_DANMU_HOST}

_CACHED_ALI_ID: str | None = None


def _generate_ali_id() -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    return "aY" + "".join(random.choice(chars) for _ in range(22))


def _ali_id() -> str:
    global _CACHED_ALI_ID
    if _CACHED_ALI_ID is None:
        _CACHED_ALI_ID = _generate_ali_id()
    return _CACHED_ALI_ID


class RenrenDanmakuProvider:
    key = "renren"

    def __init__(self, get: Callable[..., httpx.Response] = httpx.get) -> None:
        self._get = get

    def supports(self, page_url: str) -> bool:
        parsed = urlparse(page_url)
        if parsed.scheme == "renren":
            return parsed.netloc == "danmu" or parsed.path.startswith("/danmu/")
        return (parsed.hostname or "").lower() in _STATIC_HOSTS

    def search(
        self,
        name: str,
        original_name: str | None = None,
    ) -> list[DanmakuSearchItem]:
        requested_episode = extract_episode_number(original_name or name)
        results: list[DanmakuSearchItem] = []
        for series in self._search_series(name)[:8]:
            series_id = str(series.get("id") or "").strip()
            title = str(series.get("title") or series.get("name") or "").strip()
            if not series_id or not title or should_filter_name(name, title):
                continue
            for episode in self._episodes(series_id):
                episode_id = str(episode.get("sid") or episode.get("id") or "").strip()
                if not episode_id:
                    continue
                episode_no = self._int_value(episode.get("episodeNo"))
                episode_title = self._episode_title(episode, episode_no)
                candidate_name = f"{title} {episode_title}".strip()
                results.append(
                    DanmakuSearchItem(
                        provider=self.key,
                        name=candidate_name,
                        url=f"renren://danmu/{series_id}-{episode_id}",
                        resolve_context={
                            "series_id": series_id,
                            "episode_id": episode_id,
                        },
                    )
                )
        if requested_episode is None:
            return results
        matched = [
            item
            for item in results
            if extract_episode_number(item.name) == requested_episode
        ]
        return matched if matched else results[:3]

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        episode_id = self._episode_id_from_url(page_url)
        failures: list[Exception] = []
        for _tier_name, url, headers in self._tier_requests(episode_id):
            try:
                comments = self._fetch_comments(url, headers)
            except Exception as exc:
                failures.append(exc)
                continue
            if comments is None:
                continue
            return self._comment_records(comments)
        if failures:
            raise DanmakuResolveError("人人弹幕获取失败") from failures[-1]
        raise DanmakuResolveError("人人弹幕获取失败")

    def _tier_requests(self, episode_id: str) -> list[tuple[str, str, dict[str, str]]]:
        path = f"/v1/produce/danmu/EPISODE/{episode_id}"
        return [
            ("TV", f"https://{_TV_DANMU_HOST}{path}", self._tv_headers(path)),
            (
                "MAC",
                f"https://{_MAC_DANMU_HOST}{path}",
                {"User-Agent": _MAC_USER_AGENT, "Accept": "*/*"},
            ),
            (
                "WIN",
                f"https://{_MAC_DANMU_HOST}{path}",
                {"User-Agent": _WIN_USER_AGENT, "Accept": "application/json"},
            ),
            (
                "WEB",
                f"https://{_WEB_DANMU_HOST}{path}",
                {
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Origin": "https://rrsp.com.cn",
                    "Referer": "https://rrsp.com.cn/",
                },
            ),
        ]

    def _fetch_comments(self, url: str, headers: dict[str, str]) -> list[object] | None:
        response = self._get(
            url,
            headers=headers,
            timeout=10.0,
            follow_redirects=True,
        )
        if response.status_code == 404:
            payload = self._response_payload(response)
            if (
                isinstance(payload, dict)
                and payload.get("error") == "Document not found"
            ):
                return []
            return None
        payload = self._response_payload(response)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return data
        return []

    def _response_payload(self, response: httpx.Response) -> object:
        try:
            return response.json()
        except ValueError:
            return {}

    def _search_series(self, keyword: str) -> list[dict]:
        params = {
            "keywords": keyword,
            "searchAfter": "",
            "size": 30,
        }
        url = (
            f"https://{_WIN_HOST}/search/comprehensive/precise-mixed?"
            f"{urlencode(params)}"
        )
        response = self._get(
            url,
            headers=self._win_headers(),
            timeout=10.0,
            follow_redirects=True,
        )
        payload = self._response_payload(response)
        if not isinstance(payload, dict) or payload.get("code") != "0000":
            return []
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        items: list[dict] = []
        for key in ("seasonList", "fuzzySeasonList"):
            for item in data.get(key) or []:
                if isinstance(item, dict):
                    items.append(item)
        for series in data.get("seriesList") or []:
            if not isinstance(series, dict):
                continue
            for item in series.get("seasonList") or []:
                if isinstance(item, dict):
                    items.append(item)
        return self._dedupe_series(items)

    def _episodes(self, series_id: str) -> list[dict]:
        path = "/qwtv/drama/details"
        params = {
            "isAgeLimit": "false",
            "seriesId": series_id,
            "episodeId": "",
            "clarity": "HD",
            "caption": "0",
            "hevcOpen": "1",
        }
        query = urlencode(params)
        for host in (_TV_HOST, _MAC_HOST, _WIN_HOST):
            timestamp = str(int(time.time() * 1000))
            headers = self._tv_headers(path, params=params, timestamp=timestamp)
            try:
                response = self._get(
                    f"https://{host}{path}?{query}",
                    headers=headers,
                    timeout=10.0,
                    follow_redirects=True,
                )
            except Exception:
                continue
            payload = self._response_payload(response)
            if not isinstance(payload, dict) or payload.get("code") != "0000":
                continue
            data = payload.get("data")
            if not isinstance(data, dict):
                continue
            episodes = data.get("episodeList")
            if isinstance(episodes, list):
                return [episode for episode in episodes if isinstance(episode, dict)]
        return []

    def _dedupe_series(self, items: list[dict]) -> list[dict]:
        output: list[dict] = []
        seen: set[str] = set()
        for item in items:
            series_id = str(item.get("id") or "").strip()
            if not series_id or series_id in seen:
                continue
            seen.add(series_id)
            output.append(item)
        return output

    def _episode_title(self, episode: dict, episode_no: int) -> str:
        title = str(episode.get("title") or episode.get("text") or "").strip()
        if title:
            return title
        return f"第{episode_no}集" if episode_no > 0 else "正片"

    def _win_headers(self) -> dict[str, str]:
        return {
            "aliId": "".join(random.choice("0123456789ABCDEF") for _ in range(32)),
            "ct": "win_rrsp_gw",
            "cv": "1.24.2",
            "token": "",
            "Content-Type": "application/json",
            "User-Agent": _WIN_USER_AGENT,
        }

    def _tv_headers(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, str]:
        timestamp = timestamp or str(int(time.time() * 1000))
        sign = self._tv_sign(path, timestamp, params)
        return {
            "clientVersion": "1.2.2",
            "p": "Android",
            "deviceid": "tWEtIN7JG2DTDkBBigvj6A%3D%3D",
            "token": "",
            "aliid": _ali_id(),
            "umid": "",
            "clienttype": "android_qwtv_RRSP",
            "pkt": "rrmj",
            "t": timestamp,
            "sign": sign,
            "isAgree": "1",
            "et": "2",
            "Accept-Encoding": "gzip",
            "User-Agent": _TV_USER_AGENT,
        }

    def _tv_sign(
        self,
        path: str,
        timestamp: str,
        params: dict[str, str] | None = None,
    ) -> str:
        sign_text = f"{path}t{timestamp}"
        for key in sorted(params or {}):
            sign_text += f"{key}{(params or {})[key]}"
        sign_text += _TV_SECRET_KEY
        return hashlib.md5(sign_text.encode("utf-8")).hexdigest()

    def _episode_id_from_url(self, page_url: str) -> str:
        parsed = urlparse(page_url)
        if parsed.scheme == "renren":
            value = parsed.path.strip("/")
            if parsed.netloc == "danmu":
                raw_id = value
            else:
                raw_id = re.sub(r"^danmu/", "", value)
            return self._real_episode_id(raw_id)
        match = re.search(r"/v1/produce/danmu/EPISODE/([^/?#]+)", page_url)
        if match is not None:
            return self._real_episode_id(unquote(match.group(1)))
        raise DanmakuResolveError("人人弹幕地址格式不正确")

    def _real_episode_id(self, value: str) -> str:
        text = unquote(str(value or "").strip())
        if not text:
            raise DanmakuResolveError("人人弹幕地址缺少剧集 ID")
        match = re.match(r"^(?:series|\d+)-(.+)$", text, re.IGNORECASE)
        if match is not None:
            return match.group(1)
        return text

    def _comment_records(self, comments: list[object]) -> list[DanmakuRecord]:
        records = [
            record
            for record in (self._comment_record(comment) for comment in comments)
            if record is not None
        ]
        return sorted(records, key=lambda record: (record.time_offset, record.content))

    def _comment_record(self, comment: object) -> DanmakuRecord | None:
        if not isinstance(comment, dict):
            return None
        content = str(comment.get("d") or comment.get("content") or "").strip()
        if not content:
            return None
        timestamp, position, color = self._parse_p_fields(comment.get("p"))
        return DanmakuRecord(
            time_offset=timestamp,
            pos=position,
            color=str(color),
            content=content,
        )

    def _parse_p_fields(self, value: object) -> tuple[float, int, int]:
        parts = str(value or "").split(",")
        timestamp = self._float_at(parts, 0, 0.0)
        raw_mode = self._int_at(parts, 1, 1)
        color = self._int_at(parts, 3, 16777215)
        return timestamp, self._position(raw_mode), color

    def _position(self, mode: int) -> int:
        if mode == 4:
            return 4
        if mode == 5:
            return 5
        return 1

    def _float_at(self, parts: list[str], index: int, default: float) -> float:
        try:
            return float(parts[index])
        except (IndexError, TypeError, ValueError):
            return default

    def _int_at(self, parts: list[str], index: int, default: int) -> int:
        try:
            return int(float(parts[index]))
        except (IndexError, TypeError, ValueError):
            return default

    def _int_value(self, value: object) -> int:
        try:
            return int(float(str(value or "").strip()))
        except ValueError:
            return 0
