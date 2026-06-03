from __future__ import annotations

import json

from atv_player.ai.enrichment import (
    AIEnrichmentService,
    DanmakuQueryRefinementInput,
    EpisodeTitleRewriteInput,
    EpisodeTitleRewriteItem,
    FollowingDetailSummaryInput,
    MetadataQueryRefinementInput,
)
from atv_player.ai.models import AICompletionResult


class RecordingClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: list[dict[str, str]] = []

    def chat_completion(self, *, messages, temperature=0.0, response_format=None):
        self.messages = list(messages)
        self.temperature = temperature
        self.response_format = response_format
        return AICompletionResult(content=self.content)


class FailingClient:
    def chat_completion(self, **kwargs):
        raise RuntimeError("network down")


def test_refine_metadata_query_parses_json_response() -> None:
    client = RecordingClient(
        json.dumps(
            {
                "title": "黑镜",
                "year": "2011",
                "season_number": 3,
                "media_kind": "live_action",
                "alternative_titles": ["Black Mirror"],
            }
        )
    )
    service = AIEnrichmentService(client)

    result = service.refine_metadata_query(
        MetadataQueryRefinementInput(
            title="Black.Mirror.S03.2011",
            year="",
            category_name="英剧",
            season_number=0,
            source_name="browse",
        )
    )

    assert result.title == "黑镜"
    assert result.year == "2011"
    assert result.season_number == 3
    assert result.media_kind == "live_action"
    assert result.alternative_titles == ["Black Mirror"]
    assert client.response_format == {"type": "json_object"}


def test_refine_danmaku_query_parses_ordered_queries() -> None:
    client = RecordingClient(
        json.dumps(
            {
                "queries": ["黑镜 第3集", "Black Mirror S01E03"],
                "episode_number": 3,
                "reason": "clean episode marker",
            }
        )
    )
    service = AIEnrichmentService(client)

    result = service.refine_danmaku_query(
        DanmakuQueryRefinementInput(
            title="Black.Mirror.S01E03",
            media_title="黑镜",
            episode_title="",
            episode_number=0,
            year="2011",
        )
    )

    assert result.queries == ["黑镜 第3集", "Black Mirror S01E03"]
    assert result.episode_number == 3
    assert result.reason == "clean episode marker"


def test_rewrite_episode_titles_parses_index_map() -> None:
    client = RecordingClient(
        json.dumps(
            {"titles_by_index": {"0": "第一集 国歌", "1": "第二集 一千五百万点"}}
        )
    )
    service = AIEnrichmentService(client)

    result = service.rewrite_episode_titles(
        EpisodeTitleRewriteInput(
            media_title="黑镜",
            items=[
                EpisodeTitleRewriteItem(
                    index=0,
                    original_title="S01E01.mkv",
                    display_title="",
                ),
                EpisodeTitleRewriteItem(
                    index=1,
                    original_title="S01E02.mkv",
                    display_title="",
                ),
            ],
            metadata_titles={},
        )
    )

    assert result.titles_by_index == {0: "第一集 国歌", 1: "第二集 一千五百万点"}


def test_summarize_following_detail_parses_compact_summary() -> None:
    client = RecordingClient(
        json.dumps(
            {
                "summary": "本季进入主线冲突，适合继续追。",
                "highlights": ["节奏更快", "悬疑线明显", "下集将更新"],
                "next_hint": "下一集明晚更新",
            }
        )
    )
    service = AIEnrichmentService(client)

    result = service.summarize_following_detail(
        FollowingDetailSummaryInput(
            title="黑镜",
            media_kind="英剧",
            current_episode=2,
            latest_episode=3,
            total_episodes=6,
            overview="科技寓言单元剧",
            next_episode_title="",
            next_episode_air_date="2026-05-30",
            metadata_fields=[{"label": "年份", "value": "2011"}],
        )
    )

    assert result.summary == "本季进入主线冲突，适合继续追。"
    assert result.highlights == ["节奏更快", "悬疑线明显", "下集将更新"]
    assert result.next_hint == "下一集明晚更新"


def test_enrichment_returns_empty_outputs_when_client_fails() -> None:
    service = AIEnrichmentService(FailingClient())

    assert (
        service.refine_metadata_query(MetadataQueryRefinementInput(title="x")).title
        == ""
    )
    assert (
        service.refine_danmaku_query(DanmakuQueryRefinementInput(title="x")).queries
        == []
    )
    assert (
        service.rewrite_episode_titles(
            EpisodeTitleRewriteInput(media_title="x")
        ).titles_by_index
        == {}
    )
    assert (
        service.summarize_following_detail(FollowingDetailSummaryInput(title="x")).summary
        == ""
    )


def test_prompts_do_not_include_local_paths_or_api_keys() -> None:
    client = RecordingClient(json.dumps({"title": "黑镜"}))
    service = AIEnrichmentService(client)

    service.refine_metadata_query(
        MetadataQueryRefinementInput(
            title="/home/user/Videos/Black.Mirror.S01E01.mkv",
            year="2011",
            category_name="剧集",
            source_name="secret-api-key",
        )
    )

    prompt_text = "\n".join(message["content"] for message in client.messages)
    assert "/home/user" not in prompt_text
    assert "secret-api-key" not in prompt_text
    assert "Black.Mirror.S01E01.mkv" in prompt_text
