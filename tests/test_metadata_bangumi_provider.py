from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataQuery
from atv_player.metadata.providers.bangumi import BangumiMetadataProvider, is_bangumi_anime_query


class FakeBangumiClient:
    def __init__(self) -> None:
        self.search_rows: list[dict[str, object]] = []
        self.subject_detail: dict[str, object] = {}
        self.persons: list[dict[str, object]] = []
        self.characters: list[dict[str, object]] = []
        self.episodes: list[dict[str, object]] = []

    def search_subjects(self, keyword: str) -> list[dict[str, object]]:
        return list(self.search_rows)

    def get_subject(self, subject_id: int | str) -> dict[str, object]:
        return dict(self.subject_detail)

    def get_subject_persons(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self.persons)

    def get_subject_characters(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self.characters)

    def get_episodes(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self.episodes)


def _fake_vod(**overrides):
    base = {
        "vod_name": "",
        "vod_year": "",
        "category_name": "",
        "type_name": "",
        "vod_id": "",
        "dbid": 0,
        "vod_area": "",
        "vod_lang": "",
        "vod_director": "",
        "vod_actor": "",
    }
    base.update(overrides)
    return type("Vod", (), base)()


def test_is_bangumi_anime_query_uses_category_name_and_type_name() -> None:
    assert is_bangumi_anime_query(MetadataQuery(title="葬送的芙莉莲", category_name="动漫")) is True
    assert is_bangumi_anime_query(MetadataQuery(title="葬送的芙莉莲", type_name="番剧")) is True
    assert is_bangumi_anime_query(MetadataQuery(title="深空彼岸", category_name="电影")) is False


def test_bangumi_provider_can_only_enrich_anime_context() -> None:
    provider = BangumiMetadataProvider(FakeBangumiClient())

    assert provider.can_enrich(
        MetadataContext(vod=_fake_vod(vod_name="牧神记", vod_year="2024", category_name="动漫"), source_kind="browse")
    ) is True
    assert provider.can_enrich(
        MetadataContext(vod=_fake_vod(vod_name="深空彼岸", vod_year="2026", category_name="电影"), source_kind="browse")
    ) is False


def test_bangumi_provider_search_matches_name_cn_and_aliases_for_anime() -> None:
    client = FakeBangumiClient()
    client.search_rows = [
        {
            "id": 1,
            "type": 2,
            "name": "Sousou no Frieren",
            "name_cn": "葬送的芙莉莲",
            "date": "2023-09-29",
            "infobox": [{"key": "别名", "value": "Frieren"}],
        }
    ]
    provider = BangumiMetadataProvider(client)

    matches = provider.search(MetadataQuery(title="葬送的芙莉莲", year="2023", category_name="动漫"))

    assert len(matches) == 1
    assert matches[0].provider == "bangumi"
    assert matches[0].provider_id == "subject:1"
    assert matches[0].title == "葬送的芙莉莲"
    assert matches[0].year == "2023"
    assert matches[0].score >= 1.0
    assert matches[0].raw["id"] == 1
    assert matches[0].raw["categories"] == ["动漫"]
    assert matches[0].raw["aliases"] == ["Sousou no Frieren", "葬送的芙莉莲", "Frieren"]


def test_bangumi_provider_get_detail_maps_summary_people_aliases_and_episodes() -> None:
    client = FakeBangumiClient()
    client.subject_detail = {
        "id": 1,
        "name": "BanG Dream! It's MyGO!!!!!",
        "name_cn": "BanG Dream! It's MyGO!!!!!",
        "date": "2023-06-29",
        "summary": "少女乐队动画",
        "images": {"large": "https://img.example/large.jpg", "common": "https://img.example/common.jpg"},
        "rating": {"score": 8.4},
        "tags": [{"name": "动画"}, {"name": "原创"}],
        "infobox": [{"key": "别名", "value": ["迷途之子!!!!!", "MyGO!!!!!"]}, {"key": "放送开始", "value": "2023-06-29"}],
        "eps": 13,
    }
    client.persons = [{"name": "柿本广大", "relation": "导演"}, {"name": "绫奈由仁子", "relation": "系列构成"}]
    client.characters = [{"name": "高松灯", "actors": [{"name": "羊宫妃那"}]}]
    client.episodes = [{"sort": 1, "type": 0, "name_cn": "羽丘的不可思议女孩", "name": "Episode 1"}]
    provider = BangumiMetadataProvider(client)

    record = provider.get_detail(MetadataMatch(provider="bangumi", provider_id="subject:1", title="BanG Dream! It's MyGO!!!!!"))

    assert record.provider == "bangumi"
    assert record.provider_id == "subject:1"
    assert record.title == "BanG Dream! It's MyGO!!!!!"
    assert record.original_title == "BanG Dream! It's MyGO!!!!!"
    assert record.year == "2023"
    assert record.poster == "https://img.example/large.jpg"
    assert record.overview == "少女乐队动画"
    assert record.rating == "8.4"
    assert record.actors == ["羊宫妃那"]
    assert record.directors == ["柿本广大", "绫奈由仁子"]
    assert record.genres == ["动画", "原创"]
    assert record.aliases == ["BanG Dream! It's MyGO!!!!!", "迷途之子!!!!!", "MyGO!!!!!"]
    assert record.detail_fields == [
        {"label": "Bangumi ID", "value": "1"},
        {"label": "原题", "value": "BanG Dream! It's MyGO!!!!!"},
        {"label": "别名", "value": "BanG Dream! It's MyGO!!!!! / 迷途之子!!!!! / MyGO!!!!!"},
        {"label": "话数", "value": "13"},
        {"label": "放送开始", "value": "2023-06-29"},
        {"label": "声优", "value": "羊宫妃那"},
    ]
