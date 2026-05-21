# Spider Plugin Bulk Import Design

## Goal

Extend spider plugin batch import so one unified entry accepts either:

- a GitHub repository URL that contains `spiders_v2.json`
- a direct `spiders_v2.json` URL

The feature should preserve the current import summary, progress reporting, cancellation behavior, version-based skip/update behavior, and remote-plugin loading model.

## Current Context

The plugin manager already supports:

- adding one local plugin file
- adding one remote plugin file URL
- importing a GitHub repository by:
  - validating a `https://github.com/<owner>/<repo>` URL
  - resolving the repo default branch from the GitHub API
  - reading `spiders_v2.json`
  - importing each manifest entry as a remote plugin

The current implementation couples GitHub repository resolution and manifest processing inside `SpiderPluginManager.import_github_repository()`.

## Desired User Experience

Replace the GitHub-specific batch-import entry with one generic bulk-import entry.

### UI changes

- Change the plugin-manager button label from `从 GitHub 导入` to `批量导入`
- Change the input dialog title from `从 GitHub 导入` to `批量导入`
- Change the input prompt from `GitHub 仓库 URL` to `GitHub 仓库 URL 或 spiders_v2.json URL`
- Change the progress-dialog title from `从 GitHub 导入` to `批量导入`

### Accepted input forms

The bulk-import entry accepts:

- `https://github.com/<owner>/<repo>`
- any valid `http` or `https` URL pointing to a compatible `spiders_v2.json`

### Import behavior

- GitHub repository URL:
  - resolve default branch through the GitHub API
  - derive the manifest URL for `spiders_v2.json`
  - import plugins from that manifest
- Direct manifest URL:
  - fetch the manifest directly
  - import plugins from that manifest

The user still sees:

- progress updates during import
- a cancelable progress dialog
- a final summary of `新增 / 更新 / 跳过`

## Recommended Architecture

Split batch import into two layers inside `SpiderPluginManager`.

### Layer 1: source resolution

Add one unified public entry, for example `import_plugins(source_url, ...)`, that:

- accepts the raw user input URL
- detects whether it is a GitHub repository URL or a direct manifest URL
- resolves the final manifest URL
- delegates to a shared manifest-import core

### Layer 2: manifest import core

Extract the manifest-processing logic into a shared internal helper that:

- fetches and validates manifest JSON
- iterates valid manifest entries
- resolves each manifest `file` field into a final plugin source URL
- applies import/update/skip logic
- emits progress updates
- honors cancellation checks

This keeps GitHub-specific logic limited to repository resolution and allows direct manifest URLs to reuse the same import rules.

## Input Detection Rules

### GitHub repository URL

Treat the input as a GitHub repository URL only when:

- scheme is `https`
- host is `github.com`
- path contains at least two path segments

This preserves the current repository parsing behavior.

### Direct manifest URL

Any other `http` or `https` URL is treated as a direct `spiders_v2.json` URL.

### Invalid input

If the input is neither:

- a valid GitHub repository URL
- nor a valid `http/https` URL

raise a validation error:

`请输入 GitHub 仓库地址或 spiders_v2.json URL`

## Manifest Compatibility Rules

The direct manifest format remains identical to the existing `spiders_v2.json` contract.

### Top-level format

- top-level payload must be a list
- otherwise raise `spiders_v2.json 格式无效`

### Per-entry fields

Each entry continues to follow the current rules:

- `file` must be present and non-empty
- `version` must parse to a positive integer, otherwise the entry is skipped
- `valid` defaults to `True` when omitted

Entries with malformed or unsupported data should be skipped instead of aborting the whole import.

## File URL Resolution Rules

Each manifest entry resolves its `file` field into the final remote plugin source URL.

### Absolute URL entries

If `file` is an absolute `http` or `https` URL:

- use it directly as the plugin source URL

No domain restriction is applied. This is intentional for this feature.

### Relative path entries

If `file` is not an absolute URL:

- resolve it relative to the current manifest URL

Example:

- manifest URL: `https://example.com/plugins/spiders_v2.json`
- file: `py/a.txt`
- resolved plugin URL: `https://example.com/plugins/py/a.txt`

### Relative-path safety

Retain the current manifest path constraint for relative entries:

- reject absolute filesystem-style paths
- reject any relative path containing `..`

Rejected relative entries are counted as skipped.

This preserves the current guard against escaping the intended manifest directory structure.

## Import State Rules

Use the resolved final plugin source URL as the stable identity, matching current repository behavior.

### New plugin

If no plugin exists for the resolved source URL:

- create a remote plugin row
- set `enabled` from manifest `valid` with default `True`
- set `plugin_version` from manifest `version`
- derive the default display name from the resolved source URL
- refresh the plugin after insertion

### Existing plugin, same version

If a plugin already exists and `plugin_version` matches the manifest version:

- skip the entry

### Existing plugin, changed version

If a plugin already exists and the manifest version differs:

- update only the stored version and preserve existing user-managed state
- keep:
  - display name
  - enabled flag
  - config text
  - cached file path
  - existing error/load metadata
  - category overrides
- refresh the plugin after the version update

## Progress and Cancellation

Keep the current observable behavior.

### Progress stages

For GitHub repository imports:

- `resolve_repo`: `正在解析仓库信息`
- `fetch_manifest`: `正在读取 spiders_v2.json`
- `import_plugin`: `正在导入 <file>`

For direct manifest imports:

- skip the repository-resolution stage
- use:
  - `fetch_manifest`: `正在读取 spiders_v2.json`
  - `import_plugin`: `正在导入 <file>`

### Cancellation

- cancellation may occur before or during iteration
- already completed imports/updates remain persisted
- cancellation returns the same partial summary model already used today

## Error Handling

- empty input: treat as user cancel from the prompt and do nothing
- invalid source URL: show `请输入 GitHub 仓库地址或 spiders_v2.json URL`
- non-list manifest: show `spiders_v2.json 格式无效`
- per-entry fetch/load errors: count as skipped and continue

This preserves the current batch-import tolerance model.

## Code Changes

### `src/atv_player/plugins/__init__.py`

- add a generalized source parser for batch import input
- extract manifest URL resolution from GitHub repositories
- extract shared manifest import logic
- expose one unified batch-import method
- optionally keep `import_github_repository()` as a thin compatibility wrapper if that reduces churn in callers/tests

### `src/atv_player/ui/plugin_manager_dialog.py`

- rename the button and prompts from GitHub-specific wording to bulk-import wording
- switch the dialog action to call the unified batch-import method
- keep progress, cancellation, reload, and reentrancy behavior unchanged

### `README.md`

- update plugin import documentation to mention both GitHub repository import and direct `spiders_v2.json` URL import

## Test Plan

### Manager tests

Keep the existing GitHub manifest-import tests and adapt them to the unified API or a compatibility wrapper.

Add focused tests for direct manifest URLs:

- import succeeds when `file` is a relative path resolved against the manifest URL
- import succeeds when `file` is an absolute plugin URL
- entries with relative `..` paths are skipped
- invalid non-GitHub, non-HTTP input raises `请输入 GitHub 仓库地址或 spiders_v2.json URL`
- direct manifest import emits the expected progress stages without `resolve_repo`

### Dialog tests

Update UI tests to cover:

- button label `批量导入`
- prompt title `批量导入`
- prompt text `GitHub 仓库 URL 或 spiders_v2.json URL`
- progress title `批量导入`
- the dialog calling the unified batch-import method
- existing progress, cancellation, and reentrancy behavior under the renamed entry

### Documentation test scope

No new automated doc test is required. Update README text only.

## Non-Goals

- supporting non-JSON manifest formats
- supporting non-`spiders_v2.json` manifest schemas
- adding domain allowlists or trust enforcement beyond the existing warning about remote plugins
- changing how remote plugins are executed after import

## Risks and Mitigations

### Risk: duplicated logic between GitHub and manifest imports

Mitigation:

- force both paths through one shared manifest import core

### Risk: ambiguous source validation

Mitigation:

- keep GitHub detection strict
- treat all other `http/https` URLs as direct manifest URLs
- use one explicit validation error for everything else

### Risk: path traversal in relative manifest entries

Mitigation:

- preserve the existing `..` rejection rule for non-absolute entries

## Implementation Readiness

This design is intentionally narrow:

- one unified bulk-import entry
- one shared manifest import core
- one direct-manifest compatibility path

It is small enough for a single implementation plan and does not require schema changes.
