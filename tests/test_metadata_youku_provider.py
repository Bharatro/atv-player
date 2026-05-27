import httpx

from atv_player.metadata.models import MetadataQuery
from atv_player.metadata.providers.youku import YoukuMetadataProvider


def test_youku_metadata_provider_search_maps_page_component_to_series_match() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://search.youku.com/api/search"
        assert kwargs["params"]["keyword"] == "名侦探柯南"
        return httpx.Response(
            200,
            json={
                "pageComponentList": [
                    {
                        "commonData": {
                            "isYouku": 1,
                            "titleDTO": {"displayName": "名侦探柯南"},
                        },
                        "componentMap": {
                            "1035": {
                                "data": [
                                    {
                                        "videoId": "XNjUzNDA5NDEwNA==",
                                        "title": "名侦探柯南 01",
                                    }
                                ]
                            }
                        },
                    }
                ]
            },
        )

    provider = YoukuMetadataProvider(get=fake_get)

    matches = provider.search(MetadataQuery(title="名侦探柯南", year="1996", category_name="动漫"))

    assert len(matches) == 1
    assert matches[0].provider == "youku"
    assert matches[0].title == "名侦探柯南"
    assert matches[0].provider_id == "https://v.youku.com/v_show/id_XNjUzNDA5NDEwNA==.html"

    record = provider.get_detail(matches[0])

    assert record.provider == "youku"
    assert record.title == "名侦探柯南"
    assert record.detail_fields == [
        {"label": "播放链接", "value": "https://v.youku.com/v_show/id_XNjUzNDA5NDEwNA==.html"},
    ]


def test_youku_metadata_provider_search_maps_series_payload_to_series_match() -> None:
    provider = YoukuMetadataProvider(
        get=lambda url, **kwargs: httpx.Response(
            200,
            json={
                "serisesList": [
                    {
                        "videoId": "XMjQ4MTc0ODMyOA==",
                        "title": "月鳞绮纪 01",
                    }
                ]
            },
        )
    )

    matches = provider.search(MetadataQuery(title="月鳞绮纪", category_name="动漫"))

    assert [(match.title, match.provider_id) for match in matches] == [
        ("月鳞绮纪", "https://v.youku.com/v_show/id_XMjQ4MTc0ODMyOA==.html"),
    ]
