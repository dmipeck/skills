---
name: golang-uuid
description: >-
  Go UUID rules (google/uuid, uuid.Nil, uuidv7 keys, sqlc and OpenAPI
  mapping). Use when creating, parsing, mapping, or storing UUIDs.
---

# UUIDs in Go

`github.com/google/uuid`. Empty values, codegen mapping, and primary keys.

## Rules

1. **Empty UUIDs are `uuid.Nil`.** Creating or returning an empty
   `uuid.UUID` → `uuid.Nil`. Never `uuid.UUID{}`, parsed zero strings,
   or other empty-UUID workarounds.
2. **Native type at the boundary.** CLI and config pass `uuid.UUID`
   (`golang-cli`, `golang-decoupling`), not a string and not a viper type.
3. **OpenAPI.** ogen maps format `uuid` to `uuid.UUID` (`golang-api`).
4. **sqlc.** Override Postgres `uuid` to `github.com/google/uuid.UUID`
   (`golang-query`). With `emit_pointers_for_null_types`, nullable columns
   are `*uuid.UUID`. Columns with default `uuidv7()` generate non-null
   `uuid.UUID`; inserts use `RETURNING`. Selected uuid columns come back
   `uuid.UUID`.
5. **Primary key.** New tables use a uuid pk default `uuidv7()`
   (`postgres`, `golang-database`, `golang-migration`).

## Checklist

- [ ] Empty UUID is `uuid.Nil`, never `uuid.UUID{}`.
- [ ] `uuid.UUID` crosses CLI, config, OpenAPI, and sqlc boundaries.
- [ ] sqlc override is `github.com/google/uuid.UUID`.
- [ ] New table pk is uuidv7 (`postgres`).
