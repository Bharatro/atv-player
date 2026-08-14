import httpx
import pytest

from atv_player.subtitles.errors import SubtitleBlockedError, SubtitleProviderError
from atv_player.subtitles.languages import CHS
from atv_player.subtitles.models import SubtitleQuery, SubtitleSearchItem
from atv_player.subtitles.providers.zimuku import ZimukuSubtitleProvider

SEARCH_HTML = """
<html><body>
  <div class="item">
    <p class="tt"><a href="/detail/12345.html">流浪地球 简体中文</a></p>
    <span class="label">简体</span>
  </div>
  <div class="item">
    <p class="tt"><a href="/subs/67890.html">流浪地球 繁体</a></p>
    <span class="label">繁體</span>
  </div>
  <div class="item"><a href="/detail/12345.html">重复条目</a></div>
</body></html>
"""

# 实测 zimuku.org 命中风控时返回的页面特征
BLOCKED_HTML = """
<html><body><h1>网站防火墙</h1>
<p>网站访问认证页面</p><p>请输入验证码后继续访问：</p></body></html>
"""

DETAIL_HTML = '<html><body><a href="/dld/12345.html">下载字幕</a></body></html>'
DOWNLOAD_HTML = (
    '<html><body><a id="down1" href="/download/abc.zip">立即下载</a></body></html>'
)


def _provider(get) -> ZimukuSubtitleProvider:
    return ZimukuSubtitleProvider(get=get)


def test_provider_is_available_without_token() -> None:
    assert _provider(lambda *a, **k: None).available() is True


def test_search_parses_detail_links_and_dedupes() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://srtku.com/search"
        assert kwargs["params"] == {"q": "流浪地球"}
        return httpx.Response(200, text=SEARCH_HTML)

    items = _provider(fake_get).search(SubtitleQuery(title="流浪地球"))

    assert [item.subtitle_id for item in items] == ["12345", "67890"]
    assert items[0].language == CHS
    assert items[0].context["detail_url"] == "https://srtku.com/detail/12345.html"


def test_captcha_page_raises_blocked_error_not_empty_result() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(200, text=BLOCKED_HTML)

    # 必须明确报"被拦截"，否则界面会误报成"没有搜到字幕"
    with pytest.raises(SubtitleBlockedError, match="验证码"):
        _provider(fake_get).search(SubtitleQuery(title="流浪地球"))


def test_blank_keyword_skips_network() -> None:
    def fake_get(url: str, **kwargs):
        raise AssertionError("不应发起请求")

    assert _provider(fake_get).search(SubtitleQuery(title="  ")) == []


def _item() -> SubtitleSearchItem:
    return SubtitleSearchItem(
        provider="zimuku",
        provider_label="字幕库",
        subtitle_id="12345",
        name="流浪地球",
        context={"detail_url": "https://srtku.com/detail/12345.html"},
    )


def test_download_walks_detail_then_download_page() -> None:
    visited: list[str] = []

    def fake_get(url: str, **kwargs):
        visited.append(url)
        if url.endswith("/detail/12345.html"):
            return httpx.Response(200, text=DETAIL_HTML)
        if url.endswith("/dld/12345.html"):
            return httpx.Response(200, text=DOWNLOAD_HTML)
        return httpx.Response(
            200, content="1\n00:00:01,000 --> 00:00:02,000\n你好\n".encode("gb18030")
        )

    content = _provider(fake_get).download(_item())

    assert visited == [
        "https://srtku.com/detail/12345.html",
        "https://srtku.com/dld/12345.html",
        "https://srtku.com/download/abc.zip",
    ]
    assert "你好" in content.text


def test_download_blocked_at_detail_page_is_reported() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(200, text=BLOCKED_HTML)

    with pytest.raises(SubtitleBlockedError):
        _provider(fake_get).download(_item())


def test_download_without_final_link_raises() -> None:
    def fake_get(url: str, **kwargs):
        if url.endswith("/detail/12345.html"):
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(200, text="<html><body>改版了</body></html>")

    with pytest.raises(SubtitleProviderError, match="下载链接"):
        _provider(fake_get).download(_item())
