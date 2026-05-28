from __future__ import annotations

from atv_player.ai.search_intent import SmartSearchIntentParser


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = []

    def chat_completion(self, *, messages, temperature=0.0, response_format=None):
        self.messages = messages
        return type("Result", (), {"content": self.content})()


def test_intent_parser_normalizes_black_mirror_query() -> None:
    client = FakeClient(
        """
        {
          "mode": "smart_discovery",
          "media_types": ["tv"],
          "genres": ["科幻", "悬疑"],
          "rating_min": 8.0,
          "keywords": ["高分", "科幻"],
          "reference_titles": ["黑镜"],
          "sort_preference": "rating"
        }
        """
    )
    parser = SmartSearchIntentParser(client)

    intent = parser.parse("类似黑镜的高分科幻")

    assert intent.query_text == "类似黑镜的高分科幻"
    assert intent.mode == "smart_discovery"
    assert intent.media_types == ["tv"]
    assert intent.genres == ["科幻", "悬疑"]
    assert intent.rating_min == 8.0
    assert intent.keywords == ["高分", "科幻"]
    assert intent.reference_titles == ["黑镜"]
    assert intent.sort_preference == "rating"
    assert "只输出 JSON" in client.messages[0]["content"]


def test_intent_parser_falls_back_to_title_search_on_invalid_json() -> None:
    parser = SmartSearchIntentParser(FakeClient("not-json"))

    intent = parser.parse("流浪地球")

    assert intent.mode == "title_search"
    assert intent.query_text == "流浪地球"
    assert intent.keywords == ["流浪地球"]
