from __future__ import annotations

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_END = b"\x49\x45\x4E\x44\xAE\x42\x60\x82"
TS_SYNC = 0x47
TS_PACKET_SIZE = 188


def repair_segment_bytes(data: bytes) -> bytes:
    stripped = _strip_png_prefix(data)
    for source in (stripped, data) if stripped != data else (data,):
        sync_index = _find_ts_sync_offset(source)
        if sync_index < 0:
            continue
        candidate = source[sync_index:]
        aligned = _align_ts_packets(candidate)
        return aligned if aligned else candidate
    return data


def _strip_png_prefix(data: bytes) -> bytes:
    stripped = data
    while stripped.startswith(PNG_SIGNATURE):
        png_end_index = stripped.find(PNG_END)
        if png_end_index < 0:
            return data
        stripped = stripped[png_end_index + len(PNG_END) :]
    return stripped


def _align_ts_packets(data: bytes) -> bytes:
    if len(data) < TS_PACKET_SIZE:
        return data
    for offset in range(min(TS_PACKET_SIZE, len(data))):
        if data[offset] != TS_SYNC:
            continue
        probe = data[offset : offset + TS_PACKET_SIZE * 2]
        if len(probe) >= TS_PACKET_SIZE * 2 and probe[TS_PACKET_SIZE] == TS_SYNC:
            trimmed = data[offset:]
            usable = len(trimmed) - (len(trimmed) % TS_PACKET_SIZE)
            return trimmed[:usable] if usable else trimmed
    return data


def _find_ts_sync_offset(data: bytes) -> int:
    search_start = 0
    while True:
        sync_index = data.find(bytes([TS_SYNC]), search_start)
        if sync_index < 0:
            return -1
        if _looks_like_ts_payload(data[sync_index:]):
            return sync_index
        search_start = sync_index + 1


def _looks_like_ts_payload(data: bytes) -> bool:
    if len(data) < TS_PACKET_SIZE:
        return False
    if len(data) < TS_PACKET_SIZE * 2:
        return data[0] == TS_SYNC
    return data[0] == TS_SYNC and data[TS_PACKET_SIZE] == TS_SYNC
