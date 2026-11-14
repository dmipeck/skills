---
name: golang-query
description: sqlc queries in a Go app.
---
# sqlc query codegen

sqlc generates type-safe Go accessors from hand-written SQL. This skill
owns the query side; see `golang-database` (layout) and `postgres` (schema).

## Rules

1. Queries live under `internal/database/sql/` (sqlc input); generated Go
   lands in `internal/database/` (`package: database`,
   `out: ./internal/database`).
2. `sql_package: pgx/v5`. `schema` points at `./internal/migrate/sql`;
   migration files double as sqlc's schema.
3. **Avoid `pgtype.*`.** Overrides map Postgres types to native Go:
   `float64`, `time.Time`, UUID per `golang-uuid`. `pgtype` opt-in
   for weird types (e.g. `numeric`).
4. Regenerate via `internal/tools/generate.go` (see `golang-layout`):
   `//go:generate go tool sqlc generate`, run `go generate ./...`. sqlc
   pinned in `go.mod` (`tool` directive), not host/devShell install.
5. Every generated query gets an integration test (see `golang-testing`).

## sqlc.yaml

- `emit_interface: true`, `emit_empty_slices: true`.
- `emit_pointers_for_null_types: true` (optional) → nullable columns as
  pointers (`*time.Time`; UUID per `golang-uuid`) instead of `pgtype.*`.
- Columns with defaults (`now()`; UUID defaults per `golang-uuid`) generate
  non-null natives; inserts use `RETURNING`.
- `bigint`→`int64`, `float8`→`float64` are defaults, kept explicit.
- `numeric` has no lossless native type — leave `pgtype.Numeric` or map to
  string; never money through `float64`.

## Queries

- One file per aggregate. Annotate every query
  `-- name: X :one|:many|:exec|:execrows`. `$1, $2` positional params.
- Soft delete: every `SELECT` filters `deleted_at IS NULL`; "delete" is
  `UPDATE`, not `DELETE FROM` (schema side in `postgres`). UUID columns
  per `golang-uuid`; timestamps `time.Time`.

## Regenerate + verify

- `go generate ./...` (`//go:generate go tool sqlc generate` in
  `internal/tools/generate.go`), `go build ./...`,
  `go test -tags integration ./internal/database/...`.
