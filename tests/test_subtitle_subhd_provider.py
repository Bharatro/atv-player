import httpx
import pytest

from atv_player.subtitles.errors import SubtitleBlockedError, SubtitleProviderError
from atv_player.subtitles.languages import CHS_ENG
from atv_player.subtitles.models import SubtitleQuery, SubtitleSearchItem
from atv_player.subtitles.providers.subhd import SubHDSubtitleProvider

SEARCH_HTML = """
<html><body>
  <div class="box">
    <a href="/a/1001">流浪地球 简英双语</a>
    <span class="badge">简体&英文</span>
  </div>
  <div class="box">
    <a href="/a/1002">流浪地球 繁体</a>
    <span class="badge">繁體</span>
  </div>
  <div class="box"><a href="/a/1001">重复条目</a></div>
</body></html>
"""

BLOCKED_HTML = "<html><body>网站防火墙<br>请输入验证码后继续访问</body></html>"


def _provider(get=None, post=None) -> SubHDSubtitleProvider:
    return SubHDSubtitleProvider(
        get=get or (lambda *a, **k: None),
        post=post or (lambda *a, **k: None),
    )


def test_provider_is_always_available_without_token() -> None:
    assert _provider().available() is True


def test_search_parses_entries_and_dedupes() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://www.subhd.tv/search/%E6%B5%81%E6%B5%AA%E5%9C%B0%E7%90%83"
        return httpx.Response(200, text=SEARCH_HTML)

    items = _provider(get=fake_get).search(SubtitleQuery(title="流浪地球"))

    assert [item.subtitle_id for item in items] == ["1001", "1002"]
    assert items[0].language == CHS_ENG
    assert items[0].context["detail_url"] == "https://www.subhd.tv/a/1001"


def test_blocked_page_raises_blocked_error() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(200, text=BLOCKED_HTML)

    with pytest.raises(SubtitleBlockedError):
        _provider(get=fake_get).search(SubtitleQuery(title="流浪地球"))


def test_search_keeps_release_name_anchor_and_episode_fields() -> None:
    """卡片里同一个 sid 有两个锚：中文标题 + 带 SxxEyy 的发布名。

    只取第一个锚会让所有条目坍缩成同一个标题，季集信息全丢
    （用户总是下到排最前的那一集）。
    """
    html = """
    <html><body>
      <div class="box">
        <a href="/a/2001">方舟一号 第三季</a>
        <a href="/a/2001">The.Ark.S03E02.1080p.WEB.h264-BAE</a>
        <span>简英双语 SRT</span>
      </div>
      <div class="box">
        <a href="/a/2002">方舟一号 第三季</a>
        <a href="/a/2002">The.Ark.S03E06.1080p.AMZN.WEB-DL-GROUP</a>
        <span>简体</span>
      </div>
    </body></html>
    """

    def fake_get(url: str, **kwargs):
        return httpx.Response(200, text=html)

    items = _provider(get=fake_get).search(SubtitleQuery(title="方舟一号 第三季"))

    # provider 按页面顺序返回，排序由 matcher 完成
    assert [item.episode for item in items] == [2, 6]
    assert items[1].name == "方舟一号 第三季 The.Ark.S03E06.1080p.AMZN.WEB-DL-GROUP"
    assert items[1].season == 3

    from atv_player.subtitles.matcher import apply_scores

    ranked = apply_scores(
        items, SubtitleQuery(title="方舟一号 第三季", season=3, episode=6)
    )
    assert ranked[0].episode == 6


def test_search_drops_items_with_mismatched_episode() -> None:
    html = """
    <html><body>
      <div class="box">
        <a href="/a/2001">方舟一号 第三季</a>
        <a href="/a/2001">The.Ark.S03E02.1080p.WEB.h264-BAE</a>
      </div>
      <div class="box">
        <a href="/a/2002">方舟一号 第三季</a>
        <a href="/a/2002">The.Ark.S03E06.1080p.AMZN.WEB-DL-GROUP</a>
      </div>
      <div class="box">
        <a href="/a/2003">方舟一号 第三季 整季合集</a>
      </div>
    </body></html>
    """

    def fake_get(url: str, **kwargs):
        return httpx.Response(200, text=html)

    items = _provider(get=fake_get).search(
        SubtitleQuery(title="方舟一号 第三季", season=3, episode=6)
    )

    # 能判定集数且不符的丢弃；判定不出的整季包保留
    assert [item.subtitle_id for item in items] == ["2002", "2003"]
    assert items[0].episode == 6
    assert items[1].episode is None


def _item() -> SubtitleSearchItem:
    return SubtitleSearchItem(
        provider="subhd",
        provider_label="SubHD",
        subtitle_id="1001",
        name="流浪地球",
        context={"detail_url": "https://www.subhd.tv/a/1001"},
    )


def _resp(url: str, status: int, **kwargs) -> httpx.Response:
    """手动构造的 Response 要挂上 request，否则 .cookies 会抛 RuntimeError。"""
    response = httpx.Response(status, **kwargs)
    response.request = httpx.Request("GET", url)
    return response


def test_download_walks_prepare_and_down_chain_with_cookies() -> None:
    """改版后的下载链路：prepare-download → /down/ → api/sub/down → 直链。

    prepare 步骤下发的校验 cookie 必须带到后续每一步，否则 /down/ 403。
    """
    calls: list[tuple[str, dict]] = []

    def fake_get(url: str, **kwargs):
        # 记录副本：download 会在响应后原地合并新 cookie
        calls.append(
            ("GET", {"url": url, "cookies": dict(kwargs.get("cookies") or {})})
        )
        if url == "https://www.subhd.tv/a/1001":
            return _resp(url, 200, text="<html></html>")
        if url == "https://www.subhd.tv/down/1001":
            return _resp(
                url,
                200,
                headers={"Set-Cookie": "down_1001=step3token; Path=/api/sub/down"},
                text="<html></html>",
            )
        if url == "https://dl.subhd.me/2026/x.srt":
            return _resp(
                url, 200, content="1\n00:00:01,000 --> 00:00:02,000\n你好\n".encode()
            )
        raise AssertionError(f"意外的请求: {url}")

    def fake_post(url: str, **kwargs):
        calls.append(
            ("POST", {"url": url, "cookies": dict(kwargs.get("cookies") or {})})
        )
        if url == "https://www.subhd.tv/api/sub/prepare-download":
            return _resp(
                url,
                200,
                headers={"Set-Cookie": "tk_1001=sessiontoken; Path=/"},
                json={"success": True, "url": "/down/1001"},
            )
        if url == "https://www.subhd.tv/api/sub/down":
            return _resp(
                url,
                200,
                json={
                    "success": True,
                    "pass": True,
                    "msg": "验证通过",
                    "url": "https://dl.subhd.me/2026/x.srt",
                },
            )
        raise AssertionError(f"意外的请求: {url}")

    content = _provider(get=fake_get, post=fake_post).download(_item())

    assert [step for step, _ in calls] == [
        "GET",  # 详情页
        "POST",  # prepare-download
        "GET",  # /down/ 中转页
        "POST",  # api/sub/down
        "GET",  # 直链
    ]
    # prepare 下发的 cookie 要带回后续请求
    assert calls[2][1]["cookies"] == {"tk_1001": "sessiontoken"}
    assert calls[3][1]["cookies"] == {
        "tk_1001": "sessiontoken",
        "down_1001": "step3token",
    }
    # 直链不带 cookie（http_get 只在非空时才传 cookies）
    assert calls[4][1]["cookies"] == {}
    assert "你好" in content.text
    assert content.suffix == ".srt"


def test_download_surfaces_site_error_message() -> None:
    def fake_get(url: str, **kwargs):
        return _resp(url, 200, text="<html></html>")

    def fake_post(url: str, **kwargs):
        if url.endswith("/api/sub/prepare-download"):
            return _resp(
                url, 200, json={"success": False, "msg": "下载过于频繁，请稍后再试"}
            )
        raise AssertionError(f"意外的请求: {url}")

    with pytest.raises(SubtitleProviderError, match="下载过于频繁"):
        _provider(get=fake_get, post=fake_post).download(_item())


def test_download_raises_when_down_check_rejected() -> None:
    def fake_get(url: str, **kwargs):
        return _resp(url, 200, text="<html></html>")

    def fake_post(url: str, **kwargs):
        if url.endswith("/api/sub/prepare-download"):
            return _resp(
                url,
                200,
                headers={"Set-Cookie": "tk_1001=t; Path=/"},
                json={"success": True, "url": "/down/1001"},
            )
        if url.endswith("/api/sub/down"):
            return _resp(url, 200, json={"success": False, "msg": "验证失败"})
        raise AssertionError(f"意外的请求: {url}")

    with pytest.raises(SubtitleProviderError, match="验证失败"):
        _provider(get=fake_get, post=fake_post).download(_item())
