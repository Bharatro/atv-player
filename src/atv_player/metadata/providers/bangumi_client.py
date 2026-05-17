from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from atv_player.network_proxy import ProxyDecider, build_httpx_kwargs_for_url


class BangumiClient:
    _BASE_URL = "https://api.bgm.tv"
    _USER_AGENT = "ATVPlayer/1.0 (metadata integration)"

    def __init__(
        self,
        access_token: str = "",
        transport: httpx.BaseTransport | None = None,
        proxy_decider: ProxyDecider | None = None,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        self._access_token = str(access_token or "").strip()
        client_kwargs: dict[str, Any] = dict(
            base_url=self._BASE_URL,
            transport=transport,
            timeout=10.0,
        )
        client_kwargs.update(build_httpx_kwargs_for_url(proxy_decider, self._BASE_URL))
        self._client = client_factory(**client_kwargs)

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": self._USER_AGENT}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _get_json(self, path: str, *, params: dict[str, object] | None = None) -> dict[str, Any] | list[Any]:
        response = self._client.get(path, params=params, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def _post_json(self, path: str, *, json_body: dict[str, object]) -> dict[str, Any] | list[Any]:
        response = self._client.post(path, json=json_body, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def search_subjects(self, keyword: str) -> list[dict[str, object]]:
        payload = self._post_json(
            "/v0/search/subjects",
            json_body={"keyword": str(keyword or "").strip(), "filter": {"type": [2]}},
        )
        return list((payload or {}).get("data") or [])

    def get_subject(self, subject_id: int | str) -> dict[str, object]:
        return dict(self._get_json(f"/v0/subjects/{subject_id}"))

    def get_subject_persons(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self._get_json(f"/v0/subjects/{subject_id}/persons"))

    def get_subject_characters(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self._get_json(f"/v0/subjects/{subject_id}/characters"))

    def get_episodes(self, subject_id: int | str) -> list[dict[str, object]]:
        payload = self._get_json("/v0/episodes", params={"subject_id": subject_id, "type": 0})
        return list((payload or {}).get("data") or [])
