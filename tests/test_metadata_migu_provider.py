import httpx

from atv_player.metadata.models import MetadataQuery
from atv_player.metadata.providers.migu import MiguMetadataProvider


def test_migu_metadata_provider_search_maps_long_media() -> None:
    def fake_post(url: str, **kwargs):
        assert url == "https://jadeite.migu.cn/search/v3/open-search"
        assert kwargs["json"]["k"] == "深空彼岸"
        return httpx.Response(
            200,
            json={
                "body": {
                    "contentInfoList": [
                        {
                            "shortMediaAsset": {
                                "name": "深空彼岸",
                                "isLong": 1,
                                "pID": "album-1",
                                "year": "2026",
                                "contDisplayName": "动漫",
                                "h5pics": {"highResolutionV": "poster.jpg"},
                            }
                        },
                        {
                            "shortMediaAsset": {
                                "name": "深空彼岸 花絮",
                                "isLong": 0,
                                "pID": "short-1",
                            }
                        },
                    ]
                }
            },
        )

    provider = MiguMetadataProvider(post=fake_post)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026"))

    assert [(match.provider, match.provider_id, match.title, match.year) for match in matches] == [
        ("migu", "album-1", "深空彼岸", "2026")
    ]
    detail = provider.get_detail(matches[0])
    assert detail.provider == "migu"
    assert detail.title == "深空彼岸"
    assert detail.poster == "poster.jpg"
    assert detail.genres == ["动漫"]
