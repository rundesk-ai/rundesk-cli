# SQLite migrations and integrity

## Establish the migration contract

Record the engine version, current schema version, complete schema, dependent objects, row counts,
and a verified backup before changing production data:

```sql
SELECT sqlite_version();
PRAGMA user_version;
SELECT type, name, tbl_name, sql
FROM sqlite_schema
WHERE sql IS NOT NULL
ORDER BY type, name;
PRAGMA foreign_key_check;
PRAGMA quick_check;
```

Use `PRAGMA user_version` for a simple integer sequence or a migration table for identifiers and
timestamps. Do not use `schema_version`; SQLite owns it for cache invalidation. Apply a migration
and record it in the same transaction, and serialize migration runners so two processes cannot race.

## Use direct ALTER operations only when they fit

Match every operation to the runtime SQLite version:

| Operation | Minimum version | Important limit |
|---|---:|---|
| Rename a table | All SQLite 3 releases | Reference rewriting changed in 3.25–3.26; avoid `legacy_alter_table` |
| Rename a column | 3.25.0 | Fails when triggers or views become ambiguous |
| Add a column | All SQLite 3 releases | Primary key, unique, non-constant defaults, and constraint combinations are restricted |
| Drop a column | 3.35.0 | Fails if any schema object or constraint still references it |
| Set or drop `NOT NULL` | 3.53.0 | Older runtimes require a table rebuild |

Inspect the complete schema before any rename, drop, or constraint change because views, triggers,
indexes, generated columns, constraints, and foreign keys may reference the object. Some direct
operations scan or rewrite all rows even though a simple rename or unconstrained add changes only
schema text.

Do not edit `sqlite_schema` or enable `writable_schema` for ordinary application migrations. A
single invalid schema string can make the database unreadable.

## Rebuild a table with the safe sequence

Adding or removing constraints, changing a type, changing a primary key, and many column changes
require a table rebuild. Follow this order:

1. Stop competing writers and verify the backup can be opened.
2. Save the SQL for affected indexes, triggers, and views.
3. If foreign keys are enabled, set `PRAGMA foreign_keys = OFF` before the transaction; changing it
   inside a transaction is a no-op.
4. Start `BEGIN IMMEDIATE`.
5. Create `new_<table>` with the complete target schema.
6. Copy with explicit source and destination columns, conversions, and defaults. Validate row counts
   and critical aggregates before dropping anything.
7. Drop the old table. Do not rename the old table first; that can rewrite or break references.
8. Rename the new table to the original name.
9. Recreate every affected index, trigger, and view from reviewed target definitions.
10. Run `PRAGMA foreign_key_check` and abort if it returns any row.
11. Commit, then restore `PRAGMA foreign_keys = ON` and verify it returns `1`.
12. Run `PRAGMA quick_check`; use `integrity_check` for the deeper release or recovery gate.

Ensure the foreign-key setting is restored on both success and failure. Keep the original database
and backup until post-migration checks and application smoke checks pass.

## Make data transformations explicit

Never use `INSERT INTO new_table SELECT * FROM old_table`. Name both column lists so reordered or
new columns cannot silently receive the wrong data:

```sql
INSERT INTO new_account (id, email, enabled, created_at)
SELECT id,
       lower(trim(email)),
       CASE WHEN enabled THEN 1 ELSE 0 END,
       created_at
FROM account;
```

Decide what to do with rows that violate the new schema before running the migration. A conversion
that drops, truncates, or merges data needs explicit owner approval and recorded counts.

## Validate the stored result

Check the new `sqlite_schema` definitions, migration record, indexes, triggers, views, row counts,
foreign keys, and application queries. `quick_check` omits foreign-key validation, so always run
`foreign_key_check` separately. `integrity_check` reports `ok` only when its deeper checks pass;
capture and inspect every returned row instead of relying on command exit alone.

Verify the migrated database with the oldest SQLite version that must still open it. New syntax in
the schema can make an older runtime reject the entire file even when the data format is otherwise
compatible.
