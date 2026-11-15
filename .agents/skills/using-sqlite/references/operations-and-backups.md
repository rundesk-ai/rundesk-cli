# SQLite operations and backups

## Treat every live file as database state

Rollback mode may create `<db>-journal`. WAL mode uses `<db>-wal` and `<db>-shm`; committed rows may
exist only in the WAL until checkpointed. Do not delete a journal as cleanup, pair a sidecar with a
different database, or move, overwrite, rename, hard-link, or unlink a database while any connection
is open.

Keep the database on a reliable local filesystem. All processes must use compatible SQLite locking
and the same canonical path. Never inherit an open connection across `fork()`.

## Back up through SQLite

Use the host binding's online backup API for a consistent snapshot of a live database. Copy in
bounded page batches when the binding supports it so other users can progress. The backup API
replaces destination contents, so enforce the application's overwrite policy before opening the
destination and verify the completed snapshot independently.

For a compact SQL snapshot, use `VACUUM INTO` on a destination that does not already exist:

```sql
VACUUM INTO 'snapshot.db';
```

Do not use `cp` against a live database. A filesystem copy is safe only after all transactions and
connections are closed and any hot journal or WAL state remains paired with the file. Copying the
main file alone can lose committed data or produce a corrupt snapshot.

## Verify and restore deliberately

Open the backup independently, record its SQLite version and application schema version, run
`PRAGMA quick_check` plus `PRAGMA foreign_key_check`, and verify critical row counts or queries.
Periodically perform a restore rehearsal; an untested backup is only a file.

Before restore, stop every process using the destination. Preserve the failed database and all its
sidecars for diagnosis, restore to a new path, verify it, then switch the application to that path.
Never overwrite a live file under open connections.

## Maintain only from evidence

- Run `PRAGMA optimize` after index changes and at an appropriate connection lifecycle point.
- Use `PRAGMA quick_check` for routine checks and `PRAGMA integrity_check` for deeper release,
  migration, recovery, or suspected-corruption checks. Run `foreign_key_check` separately.
- Use `VACUUM` only to reclaim measured free pages, change supported file settings, or sanitize a
  copy. It rewrites the database, holds a write lock, and needs substantial temporary disk space.
  It may change rowids in tables without an explicit `INTEGER PRIMARY KEY`; never expose an
  undocumented rowid as a durable application identifier.
- Inspect WAL checkpoint results and long readers before escalating from `PASSIVE` to a blocking
  checkpoint. Never shrink a WAL by deleting it.
- Reserve free disk for the database, journals, WAL growth, migrations, and backups. `SQLITE_FULL`
  handling is part of the operational design.

Do not set `page_size`, `cache_size`, `mmap_size`, `temp_store`, `locking_mode`, or auto-vacuum from
a generic checklist. Each changes memory, compatibility, failure behavior, or file layout; measure
on the deployed runtime and filesystem first.

## Protect the file boundary

SQLite has no users, roles, or grants. Protect the containing directory and every database,
journal, WAL, shared-memory, and backup file with operating-system permissions. A common private
Unix layout is directory mode `0700` with files restricted to the service account; use platform
ACLs where mode bits do not apply.

Encryption is not built into ordinary SQLite. Use filesystem or volume encryption for at-rest
protection, encrypt backup artifacts before they leave the host, or deliberately adopt an
encrypting SQLite build when the live file needs its own encryption. Treat that build and file
format as an architectural dependency, and keep keys outside the database and repository.
