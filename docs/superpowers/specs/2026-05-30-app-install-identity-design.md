# App Install Identity Design

## Goal

Create one immutable application installation identifier and store it in the existing SQLite database for future analytics and telemetry correlation.

## Architecture

The identifier lives in a new single-row `app_identity` table in `app.db`, separate from mutable user settings in `app_config`. `SettingsRepository` owns table creation and exposes an `ensure_app_identity()` method that returns the existing identity or atomically creates it when missing.

## Identifier Format

The stored identifier is `UUID.hash`, where `UUID` is a random UUID4 string and `hash` is a short SHA-256 prefix derived from the UUID plus low-sensitivity local traits: application name, platform, machine architecture, OS release, and the database path. The hash avoids direct storage of those traits while making generated IDs include a stable feature-code component.

## Data Flow

On repository initialization, the `app_identity` table is created if needed. Application startup calls `repo.ensure_app_identity()` once after loading configuration so existing installs receive an ID without requiring login. Subsequent calls return the same stored value and never overwrite it.

## Error Handling

Identity generation uses only Python standard library functions and local database writes. If the database cannot be written, startup already fails through the existing repository initialization path.

## Testing

Storage tests verify that a new repository creates a valid `UUID.hash` identifier, that repeated calls return the same value, that a new repository instance reading the same database returns the same value, and that existing rows are not overwritten.
