from __future__ import annotations

import pytest

from atv_player.network_proxy import (
    ProxyConfig,
    ProxyDecider,
    ProxyRuleError,
    build_httpx_kwargs_for_url,
    build_requests_proxies_for_url,
    build_ytdlp_proxy_args,
)


def test_proxy_decider_returns_direct_for_bypass_host() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="socks5",
            proxy_url="socks5://127.0.0.1:1080",
            bypass_rules=["localhost", ".local", "10.0.0.0/8"],
        )
    )

    decision = decider.decide("http://10.12.0.5:4567/api/capabilities")

    assert decision.kind == "direct"
    assert decision.proxy_url == ""


def test_proxy_decider_returns_manual_proxy_for_remote_url() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="http",
            proxy_url="http://user:pass@127.0.0.1:7890",
            bypass_rules=["localhost"],
        )
    )

    decision = decider.decide("https://api.themoviedb.org/3/search/tv")

    assert decision.kind == "manual"
    assert decision.proxy_url == "http://user:pass@127.0.0.1:7890"


def test_proxy_decider_returns_system_for_non_bypass_remote_url() -> None:
    decider = ProxyDecider(ProxyConfig(mode="system", proxy_url="", bypass_rules=["127.0.0.1"]))

    decision = decider.decide("https://api.bgm.tv/v0/search/subjects")

    assert decision.kind == "system"
    assert decision.proxy_url == ""


def test_proxy_decider_returns_direct_for_non_http_url() -> None:
    decider = ProxyDecider(
        ProxyConfig(mode="http", proxy_url="http://127.0.0.1:7890", bypass_rules=[])
    )

    decision = decider.decide("file:///tmp/demo.mp4")

    assert decision.kind == "direct"


def test_build_httpx_kwargs_for_url_disables_env_for_bypass() -> None:
    decider = ProxyDecider(ProxyConfig(mode="system", proxy_url="", bypass_rules=["127.0.0.1"]))

    assert build_httpx_kwargs_for_url(decider, "http://127.0.0.1:4567/api") == {
        "trust_env": False,
    }


def test_build_requests_proxies_for_url_applies_manual_proxy() -> None:
    decider = ProxyDecider(
        ProxyConfig(mode="https", proxy_url="https://127.0.0.1:8443", bypass_rules=[])
    )

    assert build_requests_proxies_for_url(decider, "https://sec.example.com/check") == {
        "http": "https://127.0.0.1:8443",
        "https": "https://127.0.0.1:8443",
    }


def test_build_ytdlp_proxy_args_skips_bypass_targets() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="socks5",
            proxy_url="socks5://127.0.0.1:1080",
            bypass_rules=["youtu.be"],
        )
    )

    assert build_ytdlp_proxy_args(decider, "https://youtu.be/test123") == []


def test_proxy_decider_rejects_invalid_cidr_rule() -> None:
    with pytest.raises(ProxyRuleError):
        ProxyDecider(ProxyConfig(mode="direct", proxy_url="", bypass_rules=["10.0.0.0/99"]))
