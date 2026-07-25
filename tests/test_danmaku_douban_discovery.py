from atv_player.danmaku.discovery.douban import DoubanDiscovery, DoubanSubject, DoubanVendor


class JsonResponse:
    def __init__(self, payload=None, text: str = "", status_code: int = 200) -> None:
        self._payload = payload
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._payload


def test_search_subjects_parses_rexxar_items_and_smart_box() -> None:
    def fake_get(url: str, **kwargs):
        assert url.startswith("https://m.douban.com/rexxar/api/v2/search")
        assert kwargs["headers"]["Referer"] == "https://m.douban.com/movie/"
        return JsonResponse(
            {
                "subjects": {
                    "items": [
                        {
                            "layout": "subject",
                            "type_name": "电视剧",
                            "target_id": "35876897",
                            "target": {"title": "百花杀", "year": "2024"},
                        }
                    ]
                },
                "smart_box": [
                    {
                        "layout": "subject",
                        "type_name": "电影",
                        "target_id": "12345",
                        "target": {"title": "另一个剧", "year": "2023"},
                    }
                ],
            }
        )

    discovery = DoubanDiscovery(get=fake_get, post=lambda *a, **k: None)

    subjects = discovery.search_subjects("百花杀")

    assert subjects == [
        DoubanSubject(douban_id="35876897", title="百花杀", year="2024", type_name="电视剧"),
        DoubanSubject(douban_id="12345", title="另一个剧", year="2023", type_name="电影"),
    ]


def test_search_subjects_falls_back_to_public_api_when_rexxar_empty() -> None:
    def fake_get(url: str, **kwargs):
        return JsonResponse({"subjects": {"items": []}, "smart_box": []})

    def fake_post(url: str, **kwargs):
        assert url == "https://api.douban.com/v2/movie/search"
        assert kwargs["json"]["q"] == "百花杀"
        assert kwargs["json"]["apikey"]
        return JsonResponse(
            {
                "subjects": [
                    {
                        "id": 35876897,
                        "title": "百花杀",
                        "year": 2024,
                        "subtype": "tv",
                    }
                ]
            }
        )

    discovery = DoubanDiscovery(get=fake_get, post=fake_post)

    subjects = discovery.search_subjects("百花杀")

    assert subjects == [
        DoubanSubject(douban_id="35876897", title="百花杀", year="2024", type_name="电视剧"),
    ]


def test_fetch_vendors_parses_platform_media_ids_from_detail() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://m.douban.com/rexxar/api/v2/movie/35876897?for_mobile=1"
        return JsonResponse(
            {
                "vendors": [
                    {"id": "qq", "uri": "https://v.qq.com/detail/m/xyz.html?cid=mzc00200nfe7al6"},
                    {"id": "iqiyi", "uri": "https://www.iqiyi.com/v_x.html?tvid=998877"},
                    {"id": "youku", "uri": "https://v.youku.com/x?showid=556677"},
                    {"id": "bilibili", "uri": "https://www.bilibili.com/bangumi/media/md28229233"},
                ]
            }
        )

    discovery = DoubanDiscovery(get=fake_get, post=lambda *a, **k: None)

    vendors = discovery.fetch_vendors("35876897")

    assert vendors == [
        DoubanVendor(provider="tencent", media_id="mzc00200nfe7al6"),
        DoubanVendor(provider="iqiyi", media_id="998877"),
        DoubanVendor(provider="youku", media_id="556677"),
        DoubanVendor(provider="bilibili", media_id="ss28229233"),
    ]


def test_fetch_vendors_decodes_migu_content_id() -> None:
    # migu vendor uri is URL-encoded JSON; contentID must be decoded then regexed.
    encoded = "migu%3A%2F%2F%7B%22contentID%22%3A%226000000%22%7D"

    def fake_get(url: str, **kwargs):
        return JsonResponse({"vendors": [{"id": "miguvideo", "uri": encoded}]})

    discovery = DoubanDiscovery(get=fake_get, post=lambda *a, **k: None)

    vendors = discovery.fetch_vendors("35876897")

    assert vendors == [
        DoubanVendor(
            provider="migu",
            media_id="https://v3-sc.miguvideo.com/program/v4/cont/content-info/6000000/1",
        )
    ]


def test_fetch_vendors_skips_unknown_vendor_and_missing_id() -> None:
    def fake_get(url: str, **kwargs):
        return JsonResponse(
            {
                "vendors": [
                    {"id": "netflix", "uri": "https://www.netflix.com/title/80100000"},
                    {"id": "qq", "uri": "https://v.qq.com/detail/m/xyz.html"},
                ]
            }
        )

    discovery = DoubanDiscovery(get=fake_get, post=lambda *a, **k: None)

    assert discovery.fetch_vendors("35876897") == []


def test_fetch_vendors_decodes_migu_content_id_and_skips_unknown() -> None:
    # migu 的 uri 是 URL-encoded 的 JSON 片段，需 decode 后正则取 contentID；
    # 未知 vendor（如 pptv）应被跳过而不报错。
    def fake_get(url: str, **kwargs):
        return JsonResponse(
            {
                "vendors": [
                    {
                        "id": "miguvideo",
                        "uri": "migu://x?data=%7B%22contentID%22%3A%226000000%22%7D",
                    },
                    {"id": "pptv", "uri": "https://v.pptv.com/x.html"},
                ]
            }
        )

    discovery = DoubanDiscovery(get=fake_get, post=lambda *a, **k: None)

    vendors = discovery.fetch_vendors("35876897")

    assert vendors == [
        DoubanVendor(
            provider="migu",
            media_id="https://v3-sc.miguvideo.com/program/v4/cont/content-info/6000000/1",
        ),
    ]


def test_vendor_to_page_url_builds_tencent_cover_url_with_trailing_slash() -> None:
    # tencent 展开只需 cover_id，但 _extract_cover_id 的正则要求 cover id 后带斜杠，
    # 所以必须构造成 /x/cover/{cid}/ 形式，否则展开拿不到 cover_id。
    from atv_player.danmaku.discovery.douban import vendor_to_page_url

    url = vendor_to_page_url(DoubanVendor(provider="tencent", media_id="mzc00200nfe7al6"))

    assert url == "https://v.qq.com/x/cover/mzc00200nfe7al6/"


def test_vendor_to_page_url_builds_iqiyi_youku_bilibili_migu_urls() -> None:
    from atv_player.danmaku.discovery.douban import vendor_to_page_url

    assert (
        vendor_to_page_url(DoubanVendor(provider="iqiyi", media_id="998877"))
        == "https://www.iqiyi.com/v_998877.html"
    )
    assert (
        vendor_to_page_url(DoubanVendor(provider="youku", media_id="556677"))
        == "https://v.youku.com/v_show/id_556677.html"
    )
    assert (
        vendor_to_page_url(DoubanVendor(provider="bilibili", media_id="ss28229233"))
        == "https://www.bilibili.com/bangumi/play/ss28229233"
    )
    # migu media_id is already a full content-info URL; pass through unchanged.
    assert (
        vendor_to_page_url(
            DoubanVendor(
                provider="migu",
                media_id="https://v3-sc.miguvideo.com/program/v4/cont/content-info/6000000/1",
            )
        )
        == "https://v3-sc.miguvideo.com/program/v4/cont/content-info/6000000/1"
    )


def test_vendor_to_page_url_returns_empty_for_unknown_provider() -> None:
    from atv_player.danmaku.discovery.douban import vendor_to_page_url

    assert vendor_to_page_url(DoubanVendor(provider="netflix", media_id="80100000")) == ""
