from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from atv_player.danmaku.errors import DanmakuResolveError, DanmakuSearchError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.providers._concurrency import iter_bounded_settled

_KNOWN_EMPTY_CIPHERTEXT = (
    "JC+ssUOw2pdJ5AAPHofIXIGfii6fufgztv6qaxe5nyVDLrlLYrwj1AI/"
    "alkv8v4tjlnY0dMsus7PGURb5dAEDZq4F3DnE2WlVrcNcRTDTqg="
)
_KNOWN_GATEWAY_CIPHERTEXTS = {
    _KNOWN_EMPTY_CIPHERTEXT: (
        '{"code":200,"message":null,"body":{"result":[]},"timeStamp":1780275235703}'
    ),
}


def _time_to_seconds(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    parts = text.split(":")
    try:
        numbers = [int(float(part)) for part in parts]
    except ValueError:
        return 0
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0] if len(numbers) == 1 else 0


def _response_payload(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        try:
            payload = json.loads(response.text)
        except ValueError:
            raise DanmakuSearchError("咪咕响应解析失败") from exc
    if not isinstance(payload, dict):
        raise DanmakuSearchError("咪咕响应解析失败")
    return payload


def migu_decrypt(encrypted_data: str) -> str:
    text = str(encrypted_data or "").strip()
    if not text:
        return ""
    if text.startswith("{"):
        return text
    known = _KNOWN_GATEWAY_CIPHERTEXTS.get(text)
    if known is not None:
        return known

    raw = base64.b64decode(text)
    key = base64.b64decode("ALsPDrsOB7C7DAe3ur8MCwsBsAEHugC6AwAAB78KAA8=")
    for mode in ("ecb", "cbc"):
        try:
            if mode == "ecb":
                cipher = AES.new(key, AES.MODE_ECB)
            else:
                cipher = AES.new(key, AES.MODE_CBC, iv=b"\0" * AES.block_size)
            decrypted = unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8")
        except Exception:
            continue
        if decrypted.strip().startswith("{"):
            return decrypted
    raise DanmakuResolveError("咪咕弹幕响应解密失败")


class MiguDanmakuProvider:
    key = "migu"
    _SEARCH_URL = "https://jadeite.migu.cn/search/v3/open-search"
    _DETAIL_URL = "https://v3-sc.miguvideo.com/program/v4/cont/content-info/{id}/1"
    _BARRAGE_URL = (
        "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/"
        "list/{album_id}/{episode_id}"
    )
    _SEGMENT_SECONDS = 30

    def __init__(
        self,
        get: Callable[..., httpx.Response] = httpx.get,
        post: Callable[..., httpx.Response] = httpx.post,
    ) -> None:
        self._get = get
        self._post = post
        self._resolve_context_by_url: dict[str, dict[str, str | int | None]] = {}

    def supports(self, page_url: str) -> bool:
        return "miguvideo.com" in page_url or "migu.cn" in page_url

    def prime_resolve_context(
        self,
        page_url: str,
        resolve_context: dict[str, str | int | None],
    ) -> None:
        self._resolve_context_by_url[page_url] = dict(resolve_context)

    def search(
        self,
        name: str,
        original_name: str | None = None,
    ) -> list[DanmakuSearchItem]:
        response = self._post(
            self._SEARCH_URL,
            json={
                "appVersion": "6.1.1.00",
                "ct": 101,
                "isCorrectWord": 1,
                "k": name,
                "mediaSource": 9000000,
                "pageIdx": 1,
                "pageSize": 20,
                "copyrightTerminal": 3,
                "searchScene": 2,
                "uiVersion": "A3.26.0",
            },
            headers=self._json_headers(),
            timeout=10.0,
            follow_redirects=True,
        )
        payload = _response_payload(response)
        content_infos = ((payload.get("body") or {}).get("contentInfoList") or [])
        if not isinstance(content_infos, list):
            raise DanmakuSearchError("咪咕搜索结果解析失败")

        results: list[DanmakuSearchItem] = []
        for content_info in content_infos:
            if not isinstance(content_info, dict):
                continue
            asset = content_info.get("shortMediaAsset")
            if not isinstance(asset, dict) or not asset.get("isLong"):
                continue
            album_id = self._album_id(asset)
            title = str(asset.get("name") or "").strip()
            if not album_id or not title:
                continue
            for episode in self._episodes(album_id):
                episode_id = str(episode.get("pID") or "").strip()
                if not episode_id:
                    continue
                episode_name = str(episode.get("name") or "").strip()
                duration = _time_to_seconds(episode.get("duration"))
                url = self._barrage_url(album_id, episode_id)
                results.append(
                    DanmakuSearchItem(
                        provider=self.key,
                        name=f"{title} {episode_name}".strip(),
                        url=url,
                        duration_seconds=duration,
                        resolve_context={
                            "album_id": album_id,
                            "episode_id": episode_id,
                            "duration_seconds": duration,
                        },
                    )
                )
        return results

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        album_id, episode_id = self._parse_barrage_url(page_url)
        context = dict(self._resolve_context_by_url.get(page_url) or {})
        album_id = str(context.get("album_id") or album_id).strip()
        episode_id = str(context.get("episode_id") or episode_id).strip()
        duration_seconds = int(context.get("duration_seconds") or 0)
        if duration_seconds <= 0:
            detail = self._detail(episode_id)
            album_id = str(detail.get("epsID") or album_id).strip()
            duration_seconds = _time_to_seconds(
                (detail.get("playing") or {}).get("duration")
            )
        if not album_id or not episode_id:
            raise DanmakuResolveError("咪咕弹幕地址缺少视频 ID")
        if duration_seconds <= 0:
            raise DanmakuResolveError("咪咕弹幕缺少视频时长")

        segment_urls = [
            self._segment_url(
                album_id,
                episode_id,
                start,
                min(start + self._SEGMENT_SECONDS, duration_seconds),
            )
            for start in range(0, duration_seconds, self._SEGMENT_SECONDS)
        ]
        records: list[DanmakuRecord] = []
        failures = 0
        for batch in iter_bounded_settled(
            segment_urls,
            self._fetch_segment_records,
            max_workers=8,
        ):
            for settled in batch:
                if settled.error is not None:
                    failures += 1
                    continue
                records.extend(settled.value or [])
        if not records and failures:
            raise DanmakuResolveError("咪咕弹幕分段解析失败")
        return sorted(records, key=lambda record: (record.time_offset, record.content))

    def _album_id(self, asset: dict) -> str:
        extra_data = asset.get("extraData")
        if isinstance(extra_data, dict):
            episodes = extra_data.get("episodes")
            if isinstance(episodes, list) and episodes:
                return str(episodes[0] or "").strip()
        return str(asset.get("pID") or "").strip()

    def _episodes(self, album_id: str) -> list[dict]:
        payload = self._detail(album_id)
        data = (payload.get("body") or {}).get("data") if "body" in payload else payload
        if not isinstance(data, dict):
            return []
        episodes = data.get("datas")
        if isinstance(episodes, list) and episodes:
            return [episode for episode in episodes if isinstance(episode, dict)]
        playing = data.get("playing")
        if isinstance(playing, dict):
            p_id = str(playing.get("pID") or "").strip()
            if p_id:
                return [
                    {
                        "name": str(data.get("name") or "").strip(),
                        "pID": p_id,
                        "duration": playing.get("duration"),
                    }
                ]
        return []

    def _detail(self, item_id: str) -> dict:
        response = self._get(
            self._DETAIL_URL.format(id=item_id),
            headers={"User-Agent": self._user_agent()},
            timeout=10.0,
            follow_redirects=True,
        )
        payload = _response_payload(response)
        data = ((payload.get("body") or {}).get("data") or {})
        return data if isinstance(data, dict) else {}

    def _fetch_segment_records(self, segment_url: str) -> list[DanmakuRecord]:
        response = self._get(
            segment_url,
            headers={
                "User-Agent": self._user_agent(),
                "appCode": "miguvideo_default_h5",
            },
            timeout=10.0,
            follow_redirects=True,
        )
        text = response.text
        try:
            payload = response.json()
        except ValueError:
            payload = json.loads(migu_decrypt(text))
        if isinstance(payload, str):
            payload = json.loads(migu_decrypt(payload))
        comments = ((payload.get("body") or {}).get("result") or [])
        if not isinstance(comments, list):
            return []
        return [
            record
            for record in (self._comment_record(comment) for comment in comments)
            if record is not None
        ]

    def _comment_record(self, comment: object) -> DanmakuRecord | None:
        if not isinstance(comment, dict):
            return None
        content = str(comment.get("msg") or "").strip()
        if not content:
            return None
        return DanmakuRecord(
            time_offset=float(comment.get("playtime") or 0),
            pos=1,
            color=str(self._color_to_int(comment.get("textcolor"))),
            content=content,
        )

    def _parse_barrage_url(self, page_url: str) -> tuple[str, str]:
        match = re.search(r"/barrage/v2/list/([^/?#]+)/([^/?#]+)", page_url)
        if match is not None:
            return match.group(1), match.group(2)
        match = re.search(r"/content-info/([^/?#]+)/1", page_url)
        if match is not None:
            item_id = match.group(1)
            return item_id, item_id
        raise DanmakuResolveError("咪咕弹幕地址格式不正确")

    def _barrage_url(self, album_id: str, episode_id: str) -> str:
        return self._BARRAGE_URL.format(album_id=album_id, episode_id=episode_id)

    def _segment_url(
        self,
        album_id: str,
        episode_id: str,
        start: int,
        end: int,
    ) -> str:
        return f"{self._barrage_url(album_id, episode_id)}/{start}/{end}/020"

    def _json_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._user_agent(),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.miguvideo.com",
            "Referer": "https://www.miguvideo.com/",
            "appId": "miguvideo",
            "terminalId": "www",
        }

    def _user_agent(self) -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
        )

    def _color_to_int(self, value: object) -> int:
        text = str(value or "").strip().lstrip("#")
        if not text:
            return 16777215
        try:
            return int(text, 16)
        except ValueError:
            return 16777215
