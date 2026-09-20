from atv_player.metadata.tmdb_pool import (
    BUILTIN_WORKER_POOL,
    OFFICIAL_API_BASE,
    WORKER_POOL_VALUE,
    build_mirror_pool,
    canonicalize_mirror_value,
    normalize_mirror_host,
    parse_mirror_pool,
    tmdb_auth_headers,
)


def test_parse_mirror_pool_sentinel_expands_builtin_pool() -> None:
    assert parse_mirror_pool(WORKER_POOL_VALUE) == list(BUILTIN_WORKER_POOL)


def test_parse_mirror_pool_splits_and_normalizes_items() -> None:
    pool = parse_mirror_pool(" https://a.com/，https://b.com/3；https://c.com/t/p/ https://a.com ")

    assert pool == ["https://a.com", "https://b.com", "https://c.com"]


def test_parse_mirror_pool_drops_invalid_items() -> None:
    assert parse_mirror_pool("not-a-url，https://ok.example.com") == ["https://ok.example.com"]
    assert parse_mirror_pool("   ") == []
    assert parse_mirror_pool("not-a-url") == []


def test_normalize_mirror_host_variants() -> None:
    assert normalize_mirror_host("https://a.com/") == "https://a.com"
    assert normalize_mirror_host("https://a.com/3") == "https://a.com"
    assert normalize_mirror_host("https://a.com/t/p") == "https://a.com"
    assert normalize_mirror_host("http://a.com") == "http://a.com"
    assert normalize_mirror_host("ftp://a.com") == ""
    assert normalize_mirror_host("") == ""


def test_canonicalize_mirror_value_keeps_sentinel_and_joins_pool() -> None:
    assert canonicalize_mirror_value(WORKER_POOL_VALUE) == WORKER_POOL_VALUE
    assert canonicalize_mirror_value("") == ""
    assert canonicalize_mirror_value(" https://a.com/,https://b.com ") == "https://a.com,https://b.com"
    assert canonicalize_mirror_value("garbage") == ""


def test_mirror_pool_rotation_round_robin() -> None:
    pool = build_mirror_pool("https://a.com,https://b.com,https://c.com")

    seen = [pool.next_api_base() for _ in range(6)]

    assert sorted(set(seen)) == ["https://a.com", "https://b.com", "https://c.com"]
    assert seen[0] == seen[3]
    assert seen[1] == seen[4]


def test_mirror_pool_single_host_short_circuits() -> None:
    pool = build_mirror_pool("https://a.com")

    assert [pool.next_api_base() for _ in range(3)] == ["https://a.com"] * 3


def test_mirror_pool_shuffles_but_keeps_membership() -> None:
    hosts = [f"https://worker-{index}.example.com" for index in range(8)]
    pool = build_mirror_pool(",".join(hosts))

    drained = [pool.next_api_base() for _ in range(len(hosts))]

    assert sorted(drained) == sorted(hosts)


def test_mirror_pool_image_rotation_skips_official_api() -> None:
    pool = build_mirror_pool(f"{OFFICIAL_API_BASE},https://w1.example.com")

    assert [pool.next_image_base() for _ in range(4)] == ["https://w1.example.com"] * 4


def test_empty_pool_falls_back_to_official() -> None:
    pool = build_mirror_pool("")

    assert not pool
    assert pool.next_api_base() == OFFICIAL_API_BASE
    assert pool.next_image_base() is None


def test_tmdb_auth_headers_carries_key_and_drops_empty() -> None:
    assert tmdb_auth_headers(" tmdb-key ") == {"X-TMDB-API-Key": "tmdb-key"}
    assert tmdb_auth_headers("") == {}
    assert tmdb_auth_headers(None) == {}
