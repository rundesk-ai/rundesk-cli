---
name: using-sqlite
description: Use when designing, querying, reviewing, migrating, tuning, backing up, verifying, or diagnosing an application that stores data in SQLite, including the embedded file lifecycle, type affinity and strict tables, foreign keys, transactions, WAL and single-writer behavior, integrity checks, FTS, lock contention, and filesystem constraints. It supplies the rules that follow from SQLite being a file-backed, dynamically typed, single-writer engine. Do not use for a client/server database or for engine-independent data modelling.
---

# Use SQLite

Treat SQLite as an embedded database engine operating on files, not as a small client/server
database. Its file lifecycle, connection settings, dynamic typing, and single-writer model define
the safe design.

## Confirm SQLite fits

Use SQLite for application-local data on one host when writes can queue and the database can live
on a reliable local filesystem. Choose a client/server database when many machines need direct
access, concurrent writers cannot wait, or one file is the wrong operational boundary. Never put a
WAL database on a network filesystem.

## Inspect before changing

Read the actual runtime and database settings; do not infer them from a package version or copied
configuration:

```sql
SELECT sqlite_version();
PRAGMA journal_mode;
PRAGMA synchronous;
PRAGMA foreign_keys;
PRAGMA busy_timeout;
```

Inspect `PRAGMA compile_options` when advice depends on an optional feature such as FTS5. State the
minimum SQLite version for any syntax the installed runtime may not support.

## Apply the connection contract

Run connection-scoped settings on every new connection, including connections created by a pool:

```sql
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

Verify both settings after applying them. `foreign_keys` cannot be changed inside a transaction.
Choose journal and synchronous modes from the durability and concurrency requirements; do not paste
a tuning bundle into every database. WAL persists in the database, while `foreign_keys`,
`busy_timeout`, and `synchronous` are connection settings.

## Preserve the engine invariants

- Keep write transactions short. SQLite permits one writer per database file; a larger connection
  pool does not add write throughput.
- Use `BEGIN IMMEDIATE` when a transaction is known to write after reading. It acquires the write
  reservation before work that would otherwise fail during a deferred lock upgrade.
- Bind every value. Runtime-selected identifiers and sort directions must come from exact
  allowlists because parameters cannot represent SQL syntax.
- Declare constraints in the schema and enable foreign keys on every connection. Index child-key
  columns; SQLite does not create those indexes.
- Treat the database, journal, WAL, and shared-memory files as one live unit. Never move, rename,
  delete, or copy them underneath open connections.
- Back up a live database through SQLite's online backup API or `VACUUM INTO`, then verify the
  resulting database. A filesystem copy is safe only when the database is quiescent and all
  required sidecars stay paired.
- Run destructive schema work only from a verified backup, inside the documented migration
  sequence, with row and integrity checks before reporting success.
- Measure query changes with representative data and `EXPLAIN QUERY PLAN`. Do not add indexes or
  PRAGMAs because they are commonly recommended.

## Load only the needed depth

- [Schema and types](references/schema-and-types.md): affinities, `STRICT`, primary keys,
  constraints, dates, booleans, and foreign keys.
- [Transactions and WAL](references/transactions-and-wal.md): transaction modes, busy handling,
  reader snapshots, checkpoints, connections, threads, and processes.
- [Migrations and integrity](references/migrations-and-integrity.md): schema versions, supported
  `ALTER TABLE` operations, safe table rebuilds, and validation.
- [Queries and indexes](references/queries-and-indexes.md): parameter binding, `LIKE`, collations,
  query plans, composite, partial, expression, and covering indexes.
- [Operations and backups](references/operations-and-backups.md): sidecar files, live backups,
  restore, maintenance, disk safety, permissions, and encryption boundaries.
- [FTS5](references/fts5.md): full-text schema choices, external-content triggers, safe queries,
  ranking, integrity checks, and rebuilds.
- [Source basis](references/sources.md): official SQLite documentation used to verify this package;
  read when reviewing, updating, or challenging a technical claim.
