from atv_player.request_headers import normalize_media_request_headers


def test_normalize_media_request_headers_adds_huya_defaults() -> None:
    assert normalize_media_request_headers("https://liveplay.huya.com/live/stream.flv") == {
        "Referer": "https://www.huya.com/",
        "User-Agent": "HYSDK(Windows,30000002)_APP(pc_exe&7080000&official)_SDK(trans&2.34.0.5795)",
    }


def test_normalize_media_request_headers_keeps_explicit_huya_headers() -> None:
    assert normalize_media_request_headers(
        "https://liveplay.huya.com/live/stream.flv",
        {
            "Referer": "https://custom.example/",
            "User-Agent": "CustomUA",
        },
    ) == {
        "Referer": "https://custom.example/",
        "User-Agent": "CustomUA",
    }
