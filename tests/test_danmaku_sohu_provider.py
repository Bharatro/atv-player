import httpx

from atv_player.danmaku.providers.sohu import SohuDanmakuProvider


def test_sohu_search_filters_trailer_noise_and_expands_episode_candidates() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://m.so.tv.sohu.com/search/pc/keyword":
            assert kwargs["params"]["key"] == "剑来"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "aid": "noise-1",
                                "album_name": "剑来预告",
                                "is_trailer": 1,
                            },
                            {
                                "aid": "200001",
                                "album_name": "剑来",
                                "year": 2026,
                                "meta": [{"txt": "动漫 | 内地 | 2026年"}],
                            },
                        ]
                    }
                },
            )
        if url == "https://pl.hd.sohu.com/videolist":
            assert kwargs["params"]["playlistid"] == "200001"
            return httpx.Response(
                200,
                json={
                    "videos": [
                        {
                            "vid": "9001",
                            "video_name": "第1集",
                            "url_html5": "https://tv.sohu.com/v/dXMvOTAwMS8=.html",
                            "playLength": 1420,
                        },
                        {
                            "vid": "9002",
                            "video_name": "第2集",
                            "url_html5": "https://tv.sohu.com/v/dXMvOTAwMi8=.html",
                            "playLength": 1438,
                        },
                    ]
                },
            )
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)

    items = provider.search("剑来", original_name="剑来 2集")

    assert [(item.provider, item.name, item.url, item.duration_seconds) for item in items] == [
        ("sohu", "剑来 第2集", "https://tv.sohu.com/v/dXMvOTAwMi8=.html", 1438),
    ]
    assert items[0].resolve_context["aid"] == "200001"
    assert items[0].resolve_context["vid"] == "9002"


def test_sohu_search_prefers_single_main_movie_candidate() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://m.so.tv.sohu.com/search/pc/keyword":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "aid": "300001",
                                "album_name": "疯狂动物城2",
                                "year": 2026,
                                "meta": [{"txt": "电影 | 美国 | 2026年"}],
                            }
                        ]
                    }
                },
            )
        if url == "https://pl.hd.sohu.com/videolist":
            return httpx.Response(
                200,
                json={
                    "videos": [
                        {
                            "vid": "movie-main",
                            "video_name": "疯狂动物城2",
                            "url_html5": "https://tv.sohu.com/v/movie-main.html",
                            "playLength": 5935,
                        },
                        {
                            "vid": "movie-trailer",
                            "video_name": "疯狂动物城2 预告片",
                            "url_html5": "https://tv.sohu.com/v/movie-trailer.html",
                            "playLength": 95,
                        },
                    ]
                },
            )
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)

    items = provider.search("疯狂动物城2")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("疯狂动物城2", "https://tv.sohu.com/v/movie-main.html", 5935),
    ]


def test_sohu_search_keeps_variety_issue_candidates() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://m.so.tv.sohu.com/search/pc/keyword":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "aid": "400001",
                                "album_name": "哈哈哈哈哈第6季",
                                "year": 2026,
                                "meta": [{"txt": "综艺 | 内地 | 2026年"}],
                            }
                        ]
                    }
                },
            )
        if url == "https://pl.hd.sohu.com/videolist":
            return httpx.Response(
                200,
                json={
                    "videos": [
                        {
                            "vid": "issue-0405",
                            "video_name": "20260405期 第1期下",
                            "url_html5": "https://tv.sohu.com/v/issue-0405.html",
                            "playLength": 5480,
                        },
                        {
                            "vid": "issue-0411",
                            "video_name": "20260411期 第2期上",
                            "url_html5": "https://tv.sohu.com/v/issue-0411.html",
                            "playLength": 5511,
                        },
                    ]
                },
            )
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)

    items = provider.search("哈哈哈哈哈第六季", original_name="哈哈哈哈哈第六季 20260411期 第2期上")

    assert [item.name for item in items] == ["哈哈哈哈哈第6季 20260411期 第2期上"]
    assert items[0].resolve_context["variety_year"] == "20260411"
