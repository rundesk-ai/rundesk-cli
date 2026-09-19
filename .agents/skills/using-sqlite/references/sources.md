# SQLite source basis

This package is a Rundesk synthesis of SQLite's official documentation. The operational guidance
is fully contained in the other local Markdown references; use this file to audit or update the
technical basis. Prefer these primary sources over blogs, copied PRAGMA bundles, or binding-specific
defaults.

## Engine fit and file model

- [Appropriate Uses For SQLite](https://www.sqlite.org/whentouse.html): local storage, high-write
  concurrency limits, and when a client/server database is the better boundary.
- [SQLite Is Serverless](https://www.sqlite.org/serverless.html): embedded process and file model.
- [How To Corrupt An SQLite Database File](https://www.sqlite.org/howtocorrupt.html): live copies,
  sidecars, renames, links, locking protocols, inherited connections, and filesystem failures.

## Schema, types, and constraints

- [Datatypes In SQLite](https://www.sqlite.org/datatype3.html): storage classes, affinity,
  conversions, date/time and Boolean representations, and collations.
- [STRICT Tables](https://www.sqlite.org/stricttables.html): allowed declared types, coercion, and
  compatibility floor.
- [CREATE TABLE](https://www.sqlite.org/lang_createtable.html): constraints, primary-key `NULL`
  behavior, rowids, defaults, and generated columns.
- [SQLite Autoincrement](https://www.sqlite.org/autoinc.html): rowid allocation and the cost and
  narrow purpose of `AUTOINCREMENT`.
- [WITHOUT ROWID](https://www.sqlite.org/withoutrowid.html): clustered primary keys, benefits,
  restrictions, and selection criteria.
- [Foreign Key Support](https://www.sqlite.org/foreignkeys.html): per-connection enforcement,
  parent-key requirements, child-key indexes, actions, and checks.

## Transactions, WAL, and PRAGMAs

- [Transaction](https://www.sqlite.org/lang_transaction.html): implicit transactions,
  `DEFERRED`, `IMMEDIATE`, `EXCLUSIVE`, snapshots, and busy failures.
- [Write-Ahead Logging](https://www.sqlite.org/wal.html): reader/writer behavior, one-writer limit,
  checkpoints, sidecars, persistence, and network-filesystem restriction.
- [Result and Error Codes](https://www.sqlite.org/rescode.html): `SQLITE_BUSY` and
  `SQLITE_BUSY_SNAPSHOT` meaning and recovery requirements.
- [PRAGMA statements](https://www.sqlite.org/pragma.html): scope and behavior of foreign keys,
  busy timeout, synchronous modes, checkpoints, integrity checks, and `optimize`.

## Migrations and operations

- [ALTER TABLE](https://www.sqlite.org/lang_altertable.html): operation version floors, direct
  rename/add/drop/constraint changes, restrictions, and the safe generalized table rebuild.
- [SQLite Backup API](https://www.sqlite.org/backup.html): consistent online snapshots and
  incremental backup behavior.
- [VACUUM](https://www.sqlite.org/lang_vacuum.html): rewrite costs, free-space requirements, and
  `VACUUM INTO` snapshots.

## Queries, indexes, and full text

- [EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html): `SCAN`, `SEARCH`, covering indexes, and
  temporary b-trees, including the warning that output format is not a stable API.
- [Query Planning](https://www.sqlite.org/queryplanner.html): multi-column leftmost prefixes,
  covering indexes, search, and sort behavior.
- [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html): table modes, external-content
  synchronization, query syntax, rank, integrity checking, rebuild, and optimize commands.

## Attribution

This package adapts `skills/sqlite-patterns/` from the Rundesk skills catalog at
<https://github.com/rundesk-ai/rundesk-skills>, commit
`680e3d720547dbb563e6e15808e15c8f5bdd4083`, published by Rundesk AI under the MIT License.
