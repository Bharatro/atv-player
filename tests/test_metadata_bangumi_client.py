import json

import httpx

from atv_player.metadata.providers.bangumi_client import BangumiClient


def test_bangumi_client_search_subjects_sends_user_agent_without_token() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content.decode() or "{}")
        assert request.url.path == "/v0/search/subjects"
        return httpx.Response(200, json={"data": [{"id": 1, "name": "葬送的芙莉莲"}]})

    client = BangumiClient(transport=httpx.MockTransport(handler))

    rows = client.search_subjects("葬送的芙莉莲")

    assert rows == [{"id": 1, "name": "葬送的芙莉莲"}]
    assert seen["path"] == "/v0/search/subjects"
    assert seen["method"] == "POST"
    assert seen["body"] == {"keyword": "葬送的芙莉莲", "filter": {"type": [2]}}
    assert "authorization" not in {key.lower() for key in seen["headers"]}
    assert "user-agent" in {key.lower() for key in seen["headers"]}


def test_bangumi_client_get_subject_uses_bearer_token_when_configured() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"id": 42, "name": "少女乐队的呐喊"})

    client = BangumiClient(access_token="bgm-token", transport=httpx.MockTransport(handler))

    subject = client.get_subject("42")

    assert subject["id"] == 42
    assert seen["path"] == "/v0/subjects/42"
    assert seen["authorization"] == "Bearer bgm-token"
