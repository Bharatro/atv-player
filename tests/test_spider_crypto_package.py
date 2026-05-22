import re
from uuid import UUID

import pytest

from atv_player.plugins.spider_crypto.errors import SecSpiderFormatError
from atv_player.plugins.spider_crypto.package import (
    SecSpiderPackage,
    generate_secspider_id,
)
from tests.secspider_fixtures import build_secspider_package


def _package_text(
    *,
    payload: str = "payload.base64:QUJD",
    include_id: bool = True,
) -> str:
    lines = [
        "// ignore",
        "//@name:[直] omofun",
        "//@version:1",
        "//@remark:",
    ]
    if include_id:
        lines.append("//@id:12345678123456781234567812345678699e")
    lines.extend(
        [
            "//@format:secspider/1",
            "//@alg:aes-256-gcm",
            "//@wrap:hkdf-aes-keywrap",
            "//@sign:ed25519",
            "//@kid:test-kid",
            "//@nonce:base64:bm9uY2U=",
            "//@ek:base64:ZWs=",
            "//@hash:sha256:" + ("a" * 64),
            "//@sig:base64:c2ln",
            "// ignore",
            payload,
        ]
    )
    return "\n".join(lines)


def test_parse_secspider_package_reads_minimal_metadata_and_payload() -> None:
    package = SecSpiderPackage.parse(_package_text())

    assert package.header("name") == "[直] omofun"
    assert package.header("version") == "1"
    assert package.header("remark") == ""
    assert package.header("id") == "12345678123456781234567812345678699e"
    assert package.header("format") == "secspider/1"
    assert package.payload_b64 == "QUJD"
    assert package.payload_bytes() == b"ABC"


def test_parse_secspider_package_rejects_missing_required_header() -> None:
    text = _package_text().replace("//@kid:test-kid\n", "")

    with pytest.raises(SecSpiderFormatError, match="missing required header: kid"):
        SecSpiderPackage.parse(text)


def test_signing_bytes_include_id_in_stable_order_and_exclude_sig() -> None:
    package = SecSpiderPackage.parse(
        _package_text().replace("//@remark:", "//@remark:hello", 1)
    )

    assert package.signing_bytes() == "\n".join(
        [
            "//@name:[直] omofun",
            "//@version:1",
            "//@remark:hello",
            "//@id:12345678123456781234567812345678699e",
            "//@format:secspider/1",
            "//@alg:aes-256-gcm",
            "//@wrap:hkdf-aes-keywrap",
            "//@sign:ed25519",
            "//@kid:test-kid",
            "//@nonce:base64:bm9uY2U=",
            "//@ek:base64:ZWs=",
            "//@hash:sha256:" + ("a" * 64),
            "payload.base64:QUJD",
        ]
    ).encode("utf-8")


def test_signing_bytes_keep_legacy_order_when_id_is_missing() -> None:
    package = SecSpiderPackage.parse(_package_text(include_id=False))

    assert package.signing_bytes() == "\n".join(
        [
            "//@name:[直] omofun",
            "//@version:1",
            "//@remark:",
            "//@format:secspider/1",
            "//@alg:aes-256-gcm",
            "//@wrap:hkdf-aes-keywrap",
            "//@sign:ed25519",
            "//@kid:test-kid",
            "//@nonce:base64:bm9uY2U=",
            "//@ek:base64:ZWs=",
            "//@hash:sha256:" + ("a" * 64),
            "payload.base64:QUJD",
        ]
    ).encode("utf-8")


def test_generate_secspider_id_appends_crc16_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "atv_player.plugins.spider_crypto.package.uuid4",
        lambda: UUID("12345678-1234-5678-1234-567812345678"),
    )

    assert (
        generate_secspider_id("Fixture Spider")
        == "1234567812345678123456781234567853df"
    )


def test_fixture_builder_generates_id_by_default() -> None:
    package_text, _ = build_secspider_package("class Spider:\n    pass\n")
    package = SecSpiderPackage.parse(package_text)

    assert re.fullmatch(r"[0-9a-f]{32}53df", package.header("id"))


def test_fixture_builder_preserves_explicit_id() -> None:
    package_text, _ = build_secspider_package(
        "class Spider:\n    pass\n",
        package_id="inherited-id",
    )
    package = SecSpiderPackage.parse(package_text)

    assert package.header("id") == "inherited-id"


def test_fixture_builder_can_emit_legacy_package_without_id() -> None:
    package_text, _ = build_secspider_package(
        "class Spider:\n    pass\n",
        package_id=None,
    )
    package = SecSpiderPackage.parse(package_text)

    assert "id" not in package.headers
