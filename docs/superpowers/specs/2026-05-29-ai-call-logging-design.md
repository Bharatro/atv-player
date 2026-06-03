# AI Call Logging Design

## Goal

Ensure every real OpenAI-compatible AI HTTP call is written to the existing application log so users can diagnose AI connectivity, latency, and failures without exposing sensitive prompt or credential data.

## Scope

The first implementation covers the shared `OpenAICompatibleClient` in `src/atv_player/ai/openai_compatible.py`.

Covered operations:

- chat completions, including smart search, enrichment, and connectivity checks
- model list requests from AI settings

Out of scope:

- logging prompt message content
- logging response content
- logging API keys or authorization headers
- adding a separate AI log file
- adding new UI controls

## Recommended Architecture

Add logging at the OpenAI-compatible client boundary because it is the single shared HTTP integration point for configured AI calls. This avoids duplicating logging across smart search, enrichment services, and settings UI.

The client should use the standard Python logger for its module and include structured extras compatible with `StructuredJsonlHandler`:

- `log_category="ai"`
- `log_source="app"`

Each operation logs a concise lifecycle:

- start: operation name, model when relevant, sanitized endpoint summary
- success: operation name, elapsed milliseconds, HTTP status
- failure: operation name, elapsed milliseconds when available, HTTP status or sanitized exception summary

`check_connectivity()` can rely on `chat_completion()` logging because it performs a chat completion request. It does not need a second HTTP-level log, but the request should remain identifiable by its short `max_tokens` connectivity payload in tests if needed.

## Data and Privacy Rules

Log only operational metadata:

- operation name, such as `chat_completion` or `list_models`
- configured model for chat completion calls
- sanitized endpoint summary derived from base URL host/path, without credentials or query secrets
- elapsed time in milliseconds
- HTTP status code
- sanitized error text

Never log:

- prompt messages
- model response content
- raw request or response JSON
- API keys
- authorization headers
- local filesystem paths

Existing error sanitization that replaces API keys in exception text should be reused or extended for log messages.

## Error Handling

Logging must not change existing behavior:

- incomplete AI config still raises the current `OpenAICompatibleError`
- HTTP status failures still raise sanitized `OpenAICompatibleError`
- transport failures still raise sanitized `OpenAICompatibleError`
- malformed AI responses still raise the existing response-shape errors

If logging itself fails through the standard logging subsystem, the AI request path should not add any explicit recovery behavior beyond normal Python logging semantics.

## Testing Strategy

Add focused tests in `tests/test_ai_openai_compatible.py`:

- successful `chat_completion()` emits AI category logs with operation, model, status, and elapsed time
- failed `chat_completion()` emits an AI failure log and does not include the API key
- successful `list_models()` emits AI category logs

Use pytest logging capture instead of writing application log files directly. Existing `StructuredJsonlHandler` tests already cover persistence of structured extras.

## Implementation Notes

Keep the implementation small:

- use `time.perf_counter()` for elapsed milliseconds
- use `urllib.parse.urlsplit()` to build a sanitized endpoint summary
- keep log levels at `INFO` for starts and successes, `WARNING` for request failures
- include enough text in `message` for the log console to be useful even without inspecting structured extras

No settings migration is required.
