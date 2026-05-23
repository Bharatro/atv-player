from atv_player.controllers.youtube_category_config import (
    YouTubeCategoryConfig,
    load_youtube_category_config,
    parse_youtube_category_config,
)
from atv_player.models import AppConfig, DoubanCategory


def test_parse_youtube_category_config_accepts_jsonc_comments_and_maps_filters() -> None:
    payload = """
    {
      // category comment
      "class": [
        {"type_id": "電影", "type_name": "電影"},
        {"type_id": "LIST:HDR,Girls HDR,Landscape HDR", "type_name": "HDR"}
      ],
      "filters": {
        "電影": [
          {
            "key": "time",
            "name": "時間",
            "value": [
              {"n": "全部", "v": ""},
              {"n": "2024", "v": "2024"}
            ]
          }
        ],
        "LIST:HDR,Girls HDR,Landscape HDR": [
          {
            "key": "tid",
            "name": "風景",
            "value": [
              {"n": "自然", "v": "hdr 大自然"}
            ]
          }
        ]
      }
    }
    """

    config = parse_youtube_category_config(payload)

    assert isinstance(config, YouTubeCategoryConfig)
    assert [category.type_id for category in config.categories] == [
        "電影",
        "LIST:HDR,Girls HDR,Landscape HDR",
    ]
    assert config.categories[0].filters[0].key == "time"
    assert config.categories[0].filters[0].options[0].value == ""
    assert config.categories[1].filters[0].key == "list_keyword"
    assert [option.value for option in config.categories[1].filters[0].options] == [
        "HDR",
        "Girls HDR",
        "Landscape HDR",
    ]
    assert config.categories[1].filters[1].key == "tid"


def test_parse_youtube_category_config_skips_malformed_entries() -> None:
    payload = """
    {
      "class": [
        {"type_id": "", "type_name": "空"},
        {"type_id": "ok", "type_name": "有效"}
      ],
      "filters": {
        "ok": [
          {"key": "", "name": "broken", "value": [{"n": "A", "v": "a"}]},
          {"key": "tid", "name": "类型", "value": [{"n": "", "v": "bad"}, {"n": "B", "v": "b"}]}
        ]
      }
    }
    """

    config = parse_youtube_category_config(payload)

    assert [category.type_id for category in config.categories] == ["ok"]
    assert len(config.categories[0].filters) == 1
    assert config.categories[0].filters[0].options[0].name == "B"


def test_load_youtube_category_config_fetches_remote_and_updates_cache() -> None:
    config = AppConfig(
        youtube_category_source_type="remote",
        youtube_category_source_value="http://example.test/youtube.json",
    )
    saved = []

    result = load_youtube_category_config(
        config,
        text_loader=lambda url: '{"class":[{"type_id":"電影","type_name":"電影"}],"filters":{}}',
        save_config=lambda: saved.append(config.youtube_category_cache_json),
        now=lambda: 123,
    )

    assert [category.type_name for category in result.categories] == ["電影"]
    assert config.youtube_category_cache_json.startswith('{"class"')
    assert config.youtube_category_cache_refreshed_at == 123
    assert config.youtube_category_cache_error == ""
    assert saved == [config.youtube_category_cache_json]


def test_load_youtube_category_config_uses_cache_when_remote_fails() -> None:
    config = AppConfig(
        youtube_category_source_type="remote",
        youtube_category_source_value="http://example.test/youtube.json",
        youtube_category_cache_json='{"class":[{"type_id":"缓存","type_name":"缓存"}],"filters":{}}',
    )

    result = load_youtube_category_config(
        config,
        text_loader=lambda _url: (_ for _ in ()).throw(RuntimeError("offline")),
        save_config=lambda: None,
    )

    assert [category.type_name for category in result.categories] == ["缓存"]
    assert config.youtube_category_cache_error == "offline"


def test_load_youtube_category_config_falls_back_to_builtin_without_cache() -> None:
    config = AppConfig(
        youtube_category_source_type="remote",
        youtube_category_source_value="http://example.test/youtube.json",
    )

    result = load_youtube_category_config(
        config,
        text_loader=lambda _url: (_ for _ in ()).throw(RuntimeError("offline")),
        save_config=lambda: None,
        builtin_categories=[DoubanCategory(type_id="cat", type_name="内置")],
    )

    assert [category.type_name for category in result.categories] == ["内置"]
