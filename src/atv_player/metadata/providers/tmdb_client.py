from __future__ import annotations

from typing import Any

import httpx


class TMDBClient:
    _BASE_URL = "https://api.themoviedb.org/3"

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        self._client = httpx.Client(
            base_url=self._BASE_URL,
            transport=transport,
            timeout=20.0,
        )
        self._image_config: dict[str, Any] | None = None

    def _request(self, path: str, **params: object) -> dict[str, Any]:
        query = {"api_key": self._api_key, "language": "zh-CN"}
        query.update({key: value for key, value in params.items() if value not in ("", None)})
        response = self._client.get(path, params=query)
        response.raise_for_status()
        return dict(response.json())

    def _image_base(self, kind: str) -> str:
        if self._image_config is None:
            self._image_config = self._request("/configuration").get("images") or {}
        sizes = list(self._image_config.get(f"{kind}_sizes") or [])
        size = sizes[-1] if sizes else "original"
        base = str(self._image_config.get("secure_base_url") or "https://image.tmdb.org/t/p/")
        return f"{base}{size}"

    def _with_image_urls(self, payload: dict[str, Any]) -> dict[str, Any]:
        detail = dict(payload)
        poster_path = str(detail.get("poster_path") or "").strip()
        backdrop_path = str(detail.get("backdrop_path") or "").strip()
        detail["poster_url"] = f"{self._image_base('poster')}{poster_path}" if poster_path else ""
        detail["backdrop_url"] = f"{self._image_base('backdrop')}{backdrop_path}" if backdrop_path else ""
        return detail

    def search_movie(self, title: str, year: str = "") -> list[dict[str, object]]:
        return list((self._request("/search/movie", query=title, year=year).get("results") or []))

    def search_tv(self, title: str, year: str = "") -> list[dict[str, object]]:
        return list((self._request("/search/tv", query=title, first_air_date_year=year).get("results") or []))

    def get_movie_detail(self, tmdb_id: str | int) -> dict[str, Any]:
        self._image_base("poster")
        payload = self._request(
            f"/movie/{tmdb_id}",
            append_to_response="external_ids,images,alternative_titles,credits",
        )
        return self._with_image_urls(payload)

    def get_tv_detail(self, tmdb_id: str | int) -> dict[str, Any]:
        self._image_base("poster")
        payload = self._request(
            f"/tv/{tmdb_id}",
            append_to_response="external_ids,images,alternative_titles,aggregate_credits",
        )
        return self._with_image_urls(payload)
