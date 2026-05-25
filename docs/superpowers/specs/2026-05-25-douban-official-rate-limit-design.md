# Douban Official Nonblocking Rate Limit Design

## Goal

Limit official Douban metadata scraping so `movie.douban.com` is contacted at most once every 10 seconds. If another official Douban scrape is attempted before 10 seconds have elapsed, skip that official Douban attempt immediately instead of sleeping, queueing, or blocking the UI/background worker.

## Current Context

Official Douban HTTP calls are centralized in `src/atv_player/metadata/providers/local_douban_client.py`:

- `LocalDoubanClient.search()` calls `_get_text()` for `https://movie.douban.com/j/subject_suggest`.
- `LocalDoubanClient.get_detail()` calls `_get_text()` for `https://movie.douban.com/subject/{id}/`.
- `OfficialDoubanProvider` catches `DoubanBlockedError` and returns no result for official Douban.
- Legacy `DoubanProvider` can still use `LocalDoubanClient` and falls back to the remote alist-tvbox Douban API when local official Douban is unavailable.

## Options

### Option A: Sleep until the 10-second interval is available

This guarantees each official request eventually runs, but it blocks metadata scraping and can make the player or background hydration feel stuck.

### Option B: Enforce a nonblocking rate limit inside `LocalDoubanClient`

Each client checks a shared official-Douban limiter before making HTTP. If the last official request was less than 10 seconds ago, it raises a skip/rate-limit exception immediately. Existing providers treat that like official Douban being unavailable for this round.

### Option C: Enforce rate limiting in each provider

This keeps the HTTP client simpler, but it duplicates logic and can miss any direct `LocalDoubanClient` usage.

## Decision

Use Option B.

`LocalDoubanClient` is the right boundary because every official Douban HTTP request already passes through `_get_text()`. The limiter should be process-wide for all `LocalDoubanClient` instances so two providers or two hydration workers cannot bypass the interval by creating separate clients.

## Behavior

- First official Douban request is allowed immediately.
- Any official Douban request less than 10 seconds after the previous allowed official request is skipped immediately.
- A skipped request must not call the HTTP transport.
- Once 10 seconds have elapsed, the next official request is allowed.
- The skip should be represented by a dedicated exception, `DoubanRateLimitedError`.
- `DoubanRateLimitedError` should subclass `DoubanBlockedError` so existing provider fallback behavior remains intact.
- The timestamp is recorded when a request is allowed, before the HTTP call. This conservatively protects Douban even if the request later fails.

## Testing

Add focused tests in `tests/test_local_douban_client.py`:

- First request sends HTTP without waiting.
- Second request within 10 seconds raises `DoubanRateLimitedError` and sends no HTTP.
- A later request at or after 10 seconds sends HTTP again.

The tests should inject a fake monotonic clock and avoid real sleeping.

