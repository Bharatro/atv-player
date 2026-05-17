from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    mode: str = "direct"
    proxy_url: str = ""
    bypass_rules: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProxyDecision:
    kind: str
    proxy_url: str = ""


class ProxyRuleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _ParsedRule:
    kind: str
    value: object


class ProxyDecider:
    def __init__(self, config: ProxyConfig) -> None:
        self._config = ProxyConfig(
            mode=str(config.mode or "").strip().lower() or "direct",
            proxy_url=str(config.proxy_url or "").strip(),
            bypass_rules=[str(rule or "").strip() for rule in config.bypass_rules if str(rule or "").strip()],
        )
        self._rules = [self._parse_rule(rule) for rule in self._config.bypass_rules]

    def decide(self, target_url: str) -> ProxyDecision:
        parsed = urlparse(str(target_url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            return ProxyDecision("direct")
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return ProxyDecision("direct")
        if self._matches_bypass(host):
            return ProxyDecision("direct")
        if self._config.mode == "direct":
            return ProxyDecision("direct")
        if self._config.mode == "system":
            return ProxyDecision("system")
        return ProxyDecision("manual", self._config.proxy_url)

    def _matches_bypass(self, host: str) -> bool:
        for rule in self._rules:
            if rule.kind == "suffix" and host.endswith(str(rule.value)):
                return True
            if rule.kind == "exact" and host == str(rule.value):
                return True
            if rule.kind == "ip":
                try:
                    ip = ipaddress.ip_address(host)
                except ValueError:
                    continue
                if ip == rule.value:
                    return True
            if rule.kind == "network":
                try:
                    ip = ipaddress.ip_address(host)
                except ValueError:
                    continue
                if ip in rule.value:
                    return True
        return False

    def _parse_rule(self, rule: str) -> _ParsedRule:
        normalized = str(rule or "").strip().lower()
        if not normalized:
            raise ProxyRuleError("empty rule")
        if normalized.startswith("."):
            return _ParsedRule("suffix", normalized)
        if "/" in normalized:
            try:
                network = ipaddress.ip_network(normalized, strict=False)
            except ValueError as exc:
                raise ProxyRuleError(f"invalid cidr rule: {rule}") from exc
            return _ParsedRule("network", network)
        try:
            return _ParsedRule("ip", ipaddress.ip_address(normalized))
        except ValueError:
            return _ParsedRule("exact", normalized)


def build_httpx_kwargs_for_url(decider: ProxyDecider | None, target_url: str) -> dict[str, object]:
    if decider is None:
        return {}
    decision = decider.decide(target_url)
    if decision.kind == "direct":
        return {"trust_env": False}
    if decision.kind == "system":
        return {"trust_env": True}
    return {"proxy": decision.proxy_url, "trust_env": False}


def build_requests_proxies_for_url(decider: ProxyDecider | None, target_url: str) -> dict[str, str | None]:
    if decider is None:
        return {}
    decision = decider.decide(target_url)
    if decision.kind == "direct":
        return {"http": None, "https": None}
    if decision.kind == "manual":
        return {"http": decision.proxy_url, "https": decision.proxy_url}
    return {}


def build_ytdlp_proxy_args(decider: ProxyDecider | None, target_url: str) -> list[str]:
    if decider is None:
        return []
    decision = decider.decide(target_url)
    if decision.kind != "manual":
        return []
    return ["--proxy", decision.proxy_url]
