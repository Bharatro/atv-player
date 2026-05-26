# TMDB Homepage Platform Link Fallback Design

## Scope

This change refines TMDB-derived playback platform links for following detail pages.

Goals:

- Preserve TMDB `watch_providers` links when present.
- Use TMDB `homepage` as a fallback playback link only for the platform whose domain matches the homepage URL.
- Require a matching platform entry in TMDB `networks` before using the homepage fallback.
- Leave non-matching platforms to their own provider searches.

Non-goals:

- No change to following detail UI layout.
- No change to provider confidence thresholds.
- No shared homepage URL across multiple platforms.

## Behavior

- TMDB playback platform entries continue to prefer explicit `watch_providers.url`.
- If a platform has no TMDB watch-provider URL, the provider may fill it from `homepage`.
- Homepage fallback is allowed only when:
  - the homepage hostname maps to a known platform key, and
  - TMDB `networks` includes the same platform.
- If `networks` contains multiple platforms, only the hostname-matching platform gets the homepage URL.
- Other platform links must still come from their own provider searches and may later override the TMDB fallback link.

## Supported Homepage Domain Mapping

- `iqiyi.com` -> `iqiyi`
- `v.qq.com` -> `tencent`
- `youku.com` -> `youku`
- `bilibili.com` -> `bilibili`
- `mgtv.com` -> `mgtv`
- `sohu.com` / `tv.sohu.com` -> `sohu`
- `miguvideo.com` / `migu.cn` -> `migu`

## Implementation Notes

- Implement this in `src/atv_player/metadata/providers/tmdb.py`.
- Normalize TMDB `watch/providers`, `homepage`, and `networks` into a single `watch_providers` detail field.
- Preserve existing explicit TMDB watch-provider URLs over homepage fallback URLs.

## Testing

- Add a provider test proving homepage fallback fills a missing matching platform link.
- Add a provider test proving explicit TMDB watch-provider URLs are not overwritten by homepage fallback.
- Add a provider test proving a single homepage URL is not copied to other network platforms in a multi-platform show.
