from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import time
from urllib.parse import parse_qs, urlparse

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


def _looks_like_media_url(value: str) -> bool:
    return bool(re.search(r"\.(m3u8|mp4|rmvb|avi|wmv|flv|mkv|webm|mov|m3u)(?!\w)", value.strip(), re.IGNORECASE))


def _normalize_headers(raw_headers) -> dict[str, str]:
    if not raw_headers:
        return {}
    if isinstance(raw_headers, Mapping):
        return {str(key): str(value) for key, value in raw_headers.items()}
    if isinstance(raw_headers, str):
        try:
            parsed = json.loads(raw_headers)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return {str(key): str(value) for key, value in parsed.items()}
    return {}


@dataclass(frozen=True, slots=True)
class BuiltInPlaybackParser:
    key: str
    label: str
    type: int
    api: str
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class BuiltInPlaybackParserResult:
    parser_key: str
    parser_label: str
    url: str
    headers: dict[str, str]


class BuiltInPlaybackParserService:
    def __init__(
        self,
        get: Callable[..., httpx.Response] = httpx.get,
        post: Callable[..., httpx.Response] = httpx.post,
    ) -> None:
        self._get = get
        self._post = post
        self._parsers = [
            BuiltInPlaybackParser(
                key="xm",
                label="虾米",
                type=0,
                api="https://jx.xmflv.com/",
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
                },
            ),
            BuiltInPlaybackParser(
                key="fish",
                label="fish",
                type=1,
                api="https://kalbim.xatut.top/kalbim2025/781718/play/video_player.php",
                headers={
                    "user-agent": "Mozilla/5.0 (Linux; Android 10; MI 8 Build/QKQ1.190828.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/83.0.4103.101 Mobile Safari/537.36 bsl/1.0;webank/h5face;webank/2.0"
                },
            ),
            BuiltInPlaybackParser(
                key="jx1",
                label="jx1",
                type=1,
                api="http://sspa8.top:8100/api/?key=1060089351&",
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
                },
            ),
            BuiltInPlaybackParser(
                key="jx2",
                label="jx2",
                type=1,
                api="http://sspa8.top:8100/api/?cat_ext=eyJmbGFnIjpbInFxIiwi6IW+6K6vIiwicWl5aSIsIueIseWlh+iJuiIsIuWlh+iJuiIsInlvdWt1Iiwi5LyY6YW3Iiwic29odSIsIuaQnOeLkCIsImxldHYiLCLkuZDop4YiLCJtZ3R2Iiwi6IqS5p6cIiwidG5tYiIsInNldmVuIiwiYmlsaWJpbGkiLCIxOTA1Il0sImhlYWRlciI6eyJVc2VyLUFnZW50Ijoib2todHRwLzQuOS4xIn19&key=星睿4k&",
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
                },
            ),
            BuiltInPlaybackParser(
                key="mg1",
                label="mg1",
                type=1,
                api="http://shybot.top/v2/video/jx/?shykey=4595a71a4e7712568edcfa43949236b42fcfcb04997788ebe7984d6da2c6a51c&qn=max&",
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
                },
            ),
            BuiltInPlaybackParser(
                key="tx1",
                label="tx1",
                type=1,
                api="http://shybot.top/v2/video/jx/?shykey=4595a71a4e7712568edcfa43949236b42fcfcb04997788ebe7984d6da2c6a51c&",
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
                },
            ),
        ]

    def parsers(self) -> list[BuiltInPlaybackParser]:
        return list(self._parsers)

    def resolve(self, flag: str, url: str, preferred_key: str = "") -> BuiltInPlaybackParserResult:
        if not url.strip():
            raise ValueError("解析失败: 缺少待解析地址")
        errors: list[str] = []
        for parser in self._ordered_parsers(url, preferred_key):
            try:
                return self._resolve_with_parser(parser, flag, url)
            except Exception as exc:
                errors.append(f"{parser.key}: {exc}")
        raise ValueError(f"解析失败: {'; '.join(errors)}")

    def _ordered_parsers(self, url: str, preferred_key: str) -> list[BuiltInPlaybackParser]:
        if self._is_xmflv_wrapper_url(url):
            return [parser for parser in self._parsers if parser.key == "xm"]
        if not preferred_key:
            return list(self._parsers)
        preferred = [parser for parser in self._parsers if parser.key == preferred_key]
        remaining = [parser for parser in self._parsers if parser.key != preferred_key]
        return [*preferred, *remaining]

    def _resolve_with_parser(self, parser: BuiltInPlaybackParser, flag: str, url: str) -> BuiltInPlaybackParserResult:
        if parser.key == "xm":
            return self._resolve_xm(parser, url)
        response = self._get(
            parser.api,
            params={"flag": flag, "url": url},
            headers=dict(parser.headers),
            timeout=15.0,
            follow_redirects=True,
        )
        payload = response.json()
        media_url = str(payload.get("url") or "").strip()
        if payload.get("parse") == 0 or payload.get("jx") == 0 or _looks_like_media_url(media_url):
            if not _looks_like_media_url(media_url):
                raise ValueError("返回地址不可播放")
            return BuiltInPlaybackParserResult(
                parser_key=parser.key,
                parser_label=parser.label,
                url=media_url,
                headers=_normalize_headers(payload.get("header") or payload.get("headers")),
            )
        raise ValueError("返回结果仍需解析")

    def _resolve_xm(self, parser: BuiltInPlaybackParser, url: str) -> BuiltInPlaybackParserResult:
        target_url = self._extract_xm_target_url(url)
        tm = str(int(time() * 1000))
        key = hashlib.md5(f"{tm}{target_url}".encode("utf-8")).hexdigest()
        headers = dict(parser.headers)
        headers.setdefault("origin", "https://jx.xmflv.com")
        headers.setdefault("referer", "https://jx.xmflv.com/")
        response = self._post(
            "https://api.hls.one:4433/Api",
            data={
                "tm": tm,
                "url": target_url,
                "key": key,
                "sign": self._build_xm_sign(key),
            },
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )
        payload = response.json()
        encrypted = str(payload.get("data") or "").strip()
        crypto_key = str(payload.get("key") or "").strip()
        crypto_iv = str(payload.get("iv") or "").strip()
        if not encrypted or not crypto_key or not crypto_iv:
            raise ValueError("xm 未返回可解密数据")
        decrypted = self._decrypt_xm_payload(encrypted, crypto_key, crypto_iv)
        media_url, media_headers = self._parse_xm_decrypted_payload(decrypted)
        if not _looks_like_media_url(media_url):
            raise ValueError("xm 返回地址不可播放")
        return BuiltInPlaybackParserResult(
            parser_key=parser.key,
            parser_label=parser.label,
            url=media_url,
            headers=media_headers,
        )

    def _is_xmflv_wrapper_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and parsed.netloc == "jx.xmflv.com" and "url" in parse_qs(parsed.query)

    def _extract_xm_target_url(self, url: str) -> str:
        if not self._is_xmflv_wrapper_url(url):
            return url
        values = parse_qs(urlparse(url).query).get("url") or []
        target_url = values[0].strip() if values else ""
        if not target_url:
            raise ValueError("xm 缺少待解析地址")
        return target_url

    def _build_xm_sign(self, key: str) -> str:
        key_material = hashlib.md5(key.encode("utf-8")).hexdigest().encode("utf-8")
        iv = b"fUU9eRmkYzsgbkEK"
        raw = key.encode("utf-8")
        padded = raw + (b"\x00" * ((AES.block_size - len(raw) % AES.block_size) % AES.block_size))
        cipher = AES.new(key_material, AES.MODE_CBC, iv)
        return base64.b64encode(cipher.encrypt(padded)).decode("utf-8")

    def _decrypt_xm_payload(self, encrypted: str, key: str, iv: str) -> str:
        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
        decrypted = cipher.decrypt(base64.b64decode(encrypted))
        return unpad(decrypted, AES.block_size).decode("utf-8")

    def _parse_xm_decrypted_payload(self, decrypted: str) -> tuple[str, dict[str, str]]:
        value = decrypted.strip()
        start = decrypted.find("{")
        if start != -1:
            payload = json.loads(decrypted[start:])
            return str(payload.get("url") or "").strip(), _normalize_headers(payload.get("header") or payload.get("headers"))
        if _looks_like_media_url(value):
            return value, {}
        raise ValueError("xm 解密结果缺少播放信息")
