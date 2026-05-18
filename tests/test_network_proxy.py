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


# --- proxy_rules tests ---


def test_proxy_rules_only_matches_listed_domains() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="socks5",
            proxy_url="socks5://127.0.0.1:1080",
            bypass_rules=[],
            proxy_rules=[".google.com", "youtube.com"],
        )
    )

    assert decider.decide("https://www.google.com/search").kind == "manual"
    assert decider.decide("https://youtube.com/watch?v=abc").kind == "manual"
    assert decider.decide("https://api.bgm.tv/v0/subjects").kind == "direct"


def test_proxy_rules_empty_proxies_everything() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="http",
            proxy_url="http://127.0.0.1:7890",
            bypass_rules=[],
            proxy_rules=[],
        )
    )

    assert decider.decide("https://api.themoviedb.org/3/search/tv").kind == "manual"
    assert decider.decide("https://api.bgm.tv/v0/subjects").kind == "manual"


def test_proxy_rules_bypass_takes_priority_over_proxy_rules() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="socks5",
            proxy_url="socks5://127.0.0.1:1080",
            bypass_rules=[".google.com"],
            proxy_rules=[".google.com", ".youtube.com"],
        )
    )

    assert decider.decide("https://www.google.com/search").kind == "direct"
    assert decider.decide("https://www.youtube.com/watch").kind == "manual"


def test_proxy_rules_suffix_matching() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="socks5",
            proxy_url="socks5://127.0.0.1:1080",
            bypass_rules=[],
            proxy_rules=[".github.com"],
        )
    )

    assert decider.decide("https://raw.githubusercontent.com/file").kind == "direct"
    assert decider.decide("https://api.github.com/repos").kind == "manual"


def test_proxy_rules_exact_matching() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="http",
            proxy_url="http://127.0.0.1:7890",
            bypass_rules=[],
            proxy_rules=["api.tmdb.org"],
        )
    )

    assert decider.decide("https://api.tmdb.org/3/movie").kind == "manual"
    assert decider.decide("https://sub.api.tmdb.org/3/movie").kind == "direct"


def test_proxy_rules_with_system_mode() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="system",
            proxy_url="",
            bypass_rules=[],
            proxy_rules=[".youtube.com"],
        )
    )

    assert decider.decide("https://www.youtube.com/watch").kind == "system"
    assert decider.decide("https://api.bgm.tv/v0/subjects").kind == "direct"


def test_proxy_rules_with_direct_mode_always_direct() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="direct",
            proxy_url="",
            bypass_rules=[],
            proxy_rules=[".youtube.com"],
        )
    )

    assert decider.decide("https://www.youtube.com/watch").kind == "direct"


def test_build_httpx_kwargs_respects_proxy_rules() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="socks5",
            proxy_url="socks5://127.0.0.1:1080",
            bypass_rules=[],
            proxy_rules=[".google.com"],
        )
    )

    assert build_httpx_kwargs_for_url(decider, "https://www.google.com/search") == {
        "proxy": "socks5://127.0.0.1:1080",
        "trust_env": False,
    }
    assert build_httpx_kwargs_for_url(decider, "https://api.bgm.tv/v0/subjects") == {
        "trust_env": False,
    }


def test_build_requests_proxies_respects_proxy_rules() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="http",
            proxy_url="http://127.0.0.1:7890",
            bypass_rules=[],
            proxy_rules=[".google.com"],
        )
    )

    assert build_requests_proxies_for_url(decider, "https://www.google.com/search") == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }
    assert build_requests_proxies_for_url(decider, "https://api.bgm.tv/v0/subjects") == {
        "http": None,
        "https": None,
    }


def test_build_ytdlp_proxy_args_respects_proxy_rules() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="socks5",
            proxy_url="socks5://127.0.0.1:1080",
            bypass_rules=[],
            proxy_rules=[".youtube.com"],
        )
    )

    assert build_ytdlp_proxy_args(decider, "https://www.youtube.com/watch") == [
        "--proxy",
        "socks5://127.0.0.1:1080",
    ]
    assert build_ytdlp_proxy_args(decider, "https://api.bgm.tv/v0/subjects") == []


def test_proxy_decider_rejects_invalid_proxy_rule() -> None:
    with pytest.raises(ProxyRuleError):
        ProxyDecider(
            ProxyConfig(mode="direct", proxy_url="", bypass_rules=[], proxy_rules=["10.0.0.0/99"])
        )
