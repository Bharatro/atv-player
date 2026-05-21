from atv_player.metadata.models import MetadataQuery
from atv_player.metadata.providers.sohu import SohuMetadataProvider


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_sohu_provider_promotes_self_made_and_collects_supplemental_flags() -> None:
    payload = {
        "status": 200,
        "data": {
            "items": [
                {
                    "show_type": 1,
                    "album_name": "<<<谁动了我的隐私>>>",
                    "year": 2026,
                    "area": "内地",
                    "desc": "简介",
                    "corner_mark": {"type": 1, "text": "自制"},
                    "isOnly": 1,
                    "isExclusive": 1,
                    "updateNotification": "18集全 · 会员尊享全集",
                    "type_links": [{"title": "悬疑"}, {"title": "剧情"}],
                    "actor_links": [{"title": "宋家腾"}, {"title": "魏千翔"}],
                    "director_links": [{"title": "羽凌旭"}],
                    "pc_detail_url": "http://tv.sohu.com/s2026/dsjsdlwdys/",
                    "ver_big_pic": "http://img.example/poster.jpg",
                }
            ]
        },
    }
    captured: list[dict[str, object]] = []

    def fake_get(url: str, *, params=None, headers=None, follow_redirects=None, timeout=None):
        captured.append(
            {
                "url": url,
                "params": dict(params or {}),
                "headers": dict(headers or {}),
                "follow_redirects": follow_redirects,
                "timeout": timeout,
            }
        )
        return _FakeResponse(payload)

    provider = SohuMetadataProvider(get=fake_get)

    matches = provider.search(MetadataQuery(title="谁动了我的隐私", year="2026", category_name="电视剧"))

    assert len(matches) == 1
    match = matches[0]
    assert match.provider == "sohu"
    assert match.provider_id == "http://tv.sohu.com/s2026/dsjsdlwdys/"
    assert match.title == "谁动了我的隐私"
    assert match.year == "2026"
    assert match.score > 0.9
    assert match.raw["title"] == "谁动了我的隐私"
    assert match.raw["genres"] == ["悬疑", "剧情"]
    assert match.raw["sohu_badges"] == ["自制", "独播", "独家"]
    assert match.raw["sohu_preferred_over_tmdb"] is True
    assert captured[0]["params"]["key"] == "谁动了我的隐私"

    record = provider.get_detail(match)

    assert record.provider == "sohu"
    assert record.title == "谁动了我的隐私"
    assert record.poster == "http://img.example/poster.jpg"
    assert record.overview == "简介"
    assert record.actors == ["宋家腾", "魏千翔"]
    assert record.directors == ["羽凌旭"]
    assert record.genres == ["悬疑", "剧情"]
    assert record.country == "内地"
    assert {"label": "搜狐标签", "value": "自制 / 独播 / 独家"} in record.detail_fields
    assert {"label": "更新状态", "value": "18集全 · 会员尊享全集"} in record.detail_fields


def test_sohu_provider_keeps_exclusive_only_as_supplemental_match() -> None:
    payload = {
        "status": 200,
        "data": {
            "items": [
                {
                    "show_type": 1,
                    "album_name": "<<<如果可以这样爱>>>（DVD版）",
                    "year": 2019,
                    "area": "内地",
                    "corner_mark": {"type": 2, "text": "独家"},
                    "isOnly": 0,
                    "isExclusive": 1,
                    "type_links": [{"title": "电视剧"}],
                    "pc_detail_url": "http://tv.sohu.com/s2019/ruguokeyizheyangai/",
                }
            ]
        },
    }

    provider = SohuMetadataProvider(get=lambda *args, **kwargs: _FakeResponse(payload))

    matches = provider.search(MetadataQuery(title="如果可以这样爱", year="2019", category_name="电视剧"))

    assert len(matches) == 1
    assert matches[0].score > 0.8
    assert matches[0].raw["sohu_badges"] == ["独家"]
    assert matches[0].raw["sohu_preferred_over_tmdb"] is False
