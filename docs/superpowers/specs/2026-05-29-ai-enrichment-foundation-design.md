# AI Enrichment Foundation Design

## Goal

Add a shared AI enrichment layer that uses the existing OpenAI-compatible API settings to improve four user-facing media workflows:

- metadata scraping
- danmaku search
- episode title rewriting
- following detail presentation

The feature is for ordinary desktop users who can paste an OpenAI-compatible endpoint, API key, and model name, but cannot deploy local models. The AI layer must be optional, best-effort, and safe to ignore when unavailable.

## Non-Goals

- No local model deployment.
- No embedding or vector index in this phase.
- No Whisper, subtitle generation, or subtitle translation in this phase.
- No AI provider-specific SDK dependency.
- No direct AI writes to persistent media records, following progress, or danmaku source choices.
- No sending API keys, local file paths, viewing history, or the full local media library to the model.

## Existing Foundation

The app already has:

- `AIProviderConfig` in `src/atv_player/ai/models.py`
- `OpenAICompatibleClient` in `src/atv_player/ai/openai_compatible.py`
- persisted AI provider settings in `AppConfig` / `SettingsRepository`
- AI settings UI in `AdvancedSettingsDialog`
- global smart search wired through `SmartSearchController`

This design builds on that foundation instead of adding another configuration path.

## Recommended Architecture

Introduce a shared AI enrichment module under `src/atv_player/ai/`.

The central service should be small and explicit:

```python
class AIEnrichmentService:
    def refine_metadata_query(...)
    def refine_danmaku_query(...)
    def rewrite_episode_titles(...)
    def summarize_following_detail(...)
```

Each method should:

- accept plain dataclass inputs with only the fields needed for the task
- call `OpenAICompatibleClient.chat_completion(...)`
- request JSON output
- parse into typed dataclass outputs
- return an empty fallback output on any exception or invalid payload

The service should not import UI classes. UI and controller layers may consume its outputs, but the AI module remains pure orchestration and parsing.

## Data Contracts

### Metadata Query Refinement

Input:

- user-entered title or original `VodItem` title
- optional year, category, season number, source name
- optional existing normalized query text

Output:

- `title`: cleaned title for provider search
- `year`: optional year string
- `season_number`: optional season number
- `media_kind`: one of `anime`, `movie`, `live_action`, or empty
- `alternative_titles`: small list of extra search titles

Usage:

Metadata scraping may try the refined query before or alongside the existing deterministic query. Existing provider matching and scoring remain authoritative.

### Danmaku Query Refinement

Input:

- playback title
- optional media title
- optional episode title
- optional episode number
- optional year

Output:

- `queries`: ordered list of safe search queries
- `episode_number`: optional parsed episode number
- `reason`: short debug string, not shown as primary UI

Usage:

Danmaku search may search the first refined query and optionally fallback queries if the original search has no usable candidates. Existing provider filters, duration checks, and ranking remain unchanged.

### Episode Title Rewrite

Input:

- media title
- ordered playlist items with index, original title, optional current display title
- optional metadata episode title map

Output:

- `titles_by_index`: mapping from playlist index to display title

Usage:

Apply AI rewritten titles only as display titles, using the existing `episode_display_title` / `episode_title_source` mechanism. AI titles must not replace `original_title`.

### Following Detail Summary

Input:

- following title
- progress numbers
- latest known episode
- next episode date/title if available
- short overview and selected metadata fields

Output:

- `summary`: one concise paragraph
- `highlights`: up to three short bullet strings
- `next_hint`: optional short next-episode hint

Usage:

The following detail page may show this content as an auxiliary AI panel. It must not change episode counts, progress, completion state, or source snapshots.

## Integration Plan By Workflow

### Metadata Scraping

Add an optional `ai_enrichment_service` dependency to the metadata scrape orchestration boundary, not to individual providers.

First phase behavior:

1. Build the existing `MetadataQuery`.
2. Ask AI for a refined query when AI is configured.
3. Run existing provider search with the refined query.
4. If refined search is empty or fails, use the existing query path.
5. Keep current scoring and compatibility filters.

This keeps provider behavior deterministic and avoids teaching each provider about AI.

### Danmaku Search

Add optional query refinement at the service/controller boundary before provider searches.

First phase behavior:

1. Build the current danmaku query exactly as today.
2. Ask AI for one or more refined queries.
3. Search refined query first when it is meaningfully different.
4. Fall back to the original query.
5. Keep existing duration, episode, provider, and source-option filtering.

### Episode Titles

Add AI as a low-priority title source in `episode_titles.py` conventions.

First phase behavior:

1. Preserve original titles with `seed_original_titles(...)`.
2. Apply existing metadata title maps first.
3. Use AI only when titles are generic, noisy, missing, or still identical to original filenames.
4. Apply via existing title-map helpers with source name `ai`.

Source priority should keep official/provider metadata above AI.

### Following Detail

Add optional AI summary generation outside core following state computation.

First phase behavior:

1. Build the deterministic `FollowingDetailSnapshot` as today.
2. Convert a privacy-safe subset into an AI summary input.
3. Render AI summary in the detail page only if present.
4. Hide the panel on failure or empty output.

This avoids coupling AI output to progress math.

## Privacy Rules

Prompts must only include the current item/task fields required for the operation. Do not include:

- API keys
- local filesystem paths
- full media library lists
- watch history outside the current item
- arbitrary plugin payloads
- raw HTTP responses

For playlist title rewriting, send only a bounded list of title strings and indexes. For following summaries, send only the current following detail fields already visible to the user.

## Error Handling

All AI enrichment calls are best-effort:

- disabled or incomplete AI config returns empty outputs
- HTTP errors return empty outputs
- invalid JSON returns empty outputs
- malformed fields are normalized or ignored
- timeout uses the existing AI request timeout config

Failures should be logged at debug or warning level depending on whether they indicate configuration problems. User workflows must continue with existing behavior.

## UI Behavior

No new required setup screen is needed. The existing AI provider settings are sufficient.

Visible UI changes should be minimal:

- metadata and danmaku improvements appear through better results, not new blocking prompts
- episode title rewrites appear in existing title display mode
- following detail may add one compact AI summary panel when content exists

When AI is disabled, the UI should look and behave as it does now.

## Testing Strategy

Unit tests:

- service parses valid JSON for all four methods
- service returns empty fallback outputs on client exceptions
- service rejects invalid shapes without raising
- prompt payload builders exclude local paths and API keys

Integration tests:

- metadata scraping can use a refined query and falls back to original query
- danmaku search can use a refined query and falls back to original query
- episode title rewriting applies only display titles and preserves originals
- following detail hides AI summary when empty and renders it when present

Regression tests:

- AI disabled keeps current behavior
- malformed AI output does not break playback, scraping, danmaku search, or following detail

## Implementation Order

1. Add typed AI enrichment input/output models and parser tests.
2. Add `AIEnrichmentService` using `OpenAICompatibleClient`.
3. Wire service construction in `AppCoordinator` when AI config is complete.
4. Add metadata query refinement at the scrape orchestration boundary.
5. Add danmaku query refinement at the danmaku service/controller boundary.
6. Add AI episode title source through existing title-map helpers.
7. Add following detail summary rendering as optional UI content.
8. Run focused tests for AI, metadata scrape, danmaku service, episode titles, following detail, app wiring, and settings regressions.

## Open Decisions

The first implementation should prefer conservative behavior:

- Refined metadata and danmaku queries are hints, not replacements.
- AI episode titles are lower priority than official/provider episode titles.
- Following summaries are display-only and never persisted in this phase.

These defaults can be revisited after real usage shows which AI outputs are reliable enough to persist or rank more strongly.
