from __future__ import annotations

from base64 import b64decode
from binascii import crc_hqx
from dataclasses import dataclass
from uuid import uuid4

from atv_player.plugins.spider_crypto.errors import SecSpiderFormatError

_REQUIRED_HEADERS = (
    "name",
    "version",
    "remark",
    "format",
    "alg",
    "wrap",
    "sign",
    "kid",
    "nonce",
    "ek",
    "hash",
    "sig",
)
_LEGACY_SIGNING_HEADERS = (
    "name",
    "version",
    "remark",
    "format",
    "alg",
    "wrap",
    "sign",
    "kid",
    "nonce",
    "ek",
    "hash",
)
_PACKAGE_HEADER_ORDER = (
    "name",
    "version",
    "remark",
    "id",
    "tags",
    "format",
    "alg",
    "wrap",
    "sign",
    "kid",
    "nonce",
    "ek",
    "hash",
    "sig",
)


def crc16_hex(text: str) -> str:
    return f"{crc_hqx(text.encode('utf-8'), 0):04x}"


def generate_secspider_id(name: str) -> str:
    return uuid4().hex + crc16_hex(name)


def iter_package_header_keys(headers: dict[str, str]) -> tuple[str, ...]:
    ordered_keys = [key for key in _PACKAGE_HEADER_ORDER if key in headers]
    ordered_keys.extend(key for key in headers if key not in _PACKAGE_HEADER_ORDER)
    return tuple(ordered_keys)


def serialize_package_text(headers: dict[str, str], payload_b64: str) -> str:
    lines = ["// ignore"]
    lines.extend(
        f"//@{key}:{headers[key]}" for key in iter_package_header_keys(headers)
    )
    lines.extend(["// ignore", f"payload.base64:{payload_b64}"])
    return "\n".join(lines)


@dataclass(slots=True)
class SecSpiderPackage:
    headers: dict[str, str]
    payload_b64: str

    @classmethod
    def parse(cls, text: str) -> SecSpiderPackage:
        headers: dict[str, str] = {}
        payload_b64 = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line == "// ignore":
                continue
            if line.startswith("//@"):
                key, sep, value = line[3:].partition(":")
                if not sep:
                    raise SecSpiderFormatError(f"invalid header line: {line}")
                if key in headers:
                    raise SecSpiderFormatError(f"duplicate header: {key}")
                headers[key] = value
                continue
            if line.startswith("payload.base64:"):
                payload_b64 = line.removeprefix("payload.base64:")
                continue
            raise SecSpiderFormatError(f"unexpected line: {line}")
        for key in _REQUIRED_HEADERS:
            if key not in headers:
                raise SecSpiderFormatError(f"missing required header: {key}")
        if not payload_b64:
            raise SecSpiderFormatError("missing payload.base64")
        if headers["format"] != "secspider/1":
            raise SecSpiderFormatError(f"unsupported format: {headers['format']}")
        return cls(headers=headers, payload_b64=payload_b64)

    def header(self, key: str) -> str:
        return self.headers[key]

    def payload_bytes(self) -> bytes:
        return b64decode(self.payload_b64)

    def decoded_header_bytes(self, key: str) -> bytes:
        raw = self.header(key)
        if not raw.startswith("base64:"):
            raise SecSpiderFormatError(f"header is not base64 encoded: {key}")
        return b64decode(raw.removeprefix("base64:"))

    def signing_bytes(self) -> bytes:
        signing_headers = list(_LEGACY_SIGNING_HEADERS)
        if "id" in self.headers:
            signing_headers.insert(3, "id")
        lines = [f"//@{key}:{self.header(key)}" for key in signing_headers]
        lines.append(f"payload.base64:{self.payload_b64}")
        return "\n".join(lines).encode("utf-8")
