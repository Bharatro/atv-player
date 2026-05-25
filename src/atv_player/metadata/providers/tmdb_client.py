from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from atv_player.network_proxy import ProxyDecider, build_httpx_kwargs_for_url


class TMDBClient:
    _BASE_URL = "https://api.themoviedb.org/3"

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        proxy_decider: ProxyDecider | None = None,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        client_kwargs: dict[str, Any] = dict(
            base_url=self._BASE_URL,
            transport=transport,
            timeout=20.0,
        )
        client_kwargs.update(build_httpx_kwargs_for_url(proxy_decider, self._BASE_URL))
        self._client = client_factory(**client_kwargs)
        self._image_config: dict[str, Any] | None = None

    def _request(self, path: str, **params: object) -> dict[str, Any]:
        query = {"api_key": self._api_key, "language": "zh-CN"}
        query.update({key: value for key, value in params.items() if value not in ("", None)})
        response = self._client.get(path, params=query)
        response.raise_for_status()
        return dict(response.json())

    def image_base(self, kind: str) -> str:
        if self._image_config is None:
            self._image_config = self._request("/configuration").get("images") or {}
        sizes = list(self._image_config.get(f"{kind}_sizes") or [])
        size = "original" if kind == "poster" else (sizes[-1] if sizes else "original")
        base = str(self._image_config.get("secure_base_url") or "https://image.tmdb.org/t/p/")
        return f"{base}{size}"

    def _image_base(self, kind: str) -> str:
        return self.image_base(kind)

    def _with_image_urls(self, payload: dict[str, Any]) -> dict[str, Any]:
        detail = dict(payload)
        poster_path = str(detail.get("poster_path") or "").strip()
        backdrop_path = str(detail.get("backdrop_path") or "").strip()
        detail["poster_url"] = f"{self.image_base('poster')}{poster_path}" if poster_path else ""
        detail["backdrop_url"] = f"{self.image_base('backdrop')}{backdrop_path}" if backdrop_path else ""
        return detail

    def _with_episode_still_urls(
        self,
        payload: dict[str, Any],
        *,
        season_number: int,
    ) -> dict[str, Any]:
        detail = dict(payload)
        episodes: list[dict[str, Any]] = []
        still_base = ""
        for episode in detail.get("episodes") or []:
            row = dict(episode)
            still_path = str(row.get("still_path") or "").strip()
            if still_path and not still_base:
                still_base = self._image_base("backdrop")
            row["still_url"] = f"{still_base}{still_path}" if still_path else ""
            row["season_number"] = season_number
            episodes.append(row)
        detail["episodes"] = episodes
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

    def get_tv_detail_with_season(self, tmdb_id: str | int, *, season_number: int | None = None) -> dict[str, Any]:
        self._image_base("poster")
        parts = ["external_ids", "images", "alternative_titles", "credits"]
        if season_number is not None and season_number > 0:
            parts.append(f"season/{season_number}")
        payload = self._request(
            f"/tv/{tmdb_id}",
            append_to_response=",".join(parts),
        )
        detail = self._with_image_urls(payload)
        season_key = f"season/{season_number}" if season_number is not None and season_number > 0 else ""
        if season_key and isinstance(detail.get(season_key), dict):
            detail[season_key] = self._with_episode_still_urls(
                detail[season_key],
                season_number=season_number,
            )
        return detail

    def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict[str, Any]:
        payload = self._request(f"/tv/{tmdb_id}/season/{season_number}")
        return self._with_episode_still_urls(payload, season_number=season_number)
