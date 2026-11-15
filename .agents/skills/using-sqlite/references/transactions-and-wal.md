# SQLite transactions and WAL

## Work with one writer

SQLite permits many readers but one write transaction per database file. WAL lets readers continue
while that writer appends changes; it does not create concurrent writers. Reduce contention with
short transactions, batched writes, and a bounded busy timeout—not more pooled connections.

Keep network requests, user prompts, slow computation, and unbounded iteration outside a write
transaction. Finalize cursors and incremental BLOB handles promptly because unfinished statements
can keep transactions and snapshots open.

## Choose the transaction mode

```sql
BEGIN;             -- DEFERRED: lock type follows the first operation
BEGIN IMMEDIATE;   -- reserve the writer before doing transaction work
BEGIN EXCLUSIVE;   -- like IMMEDIATE in WAL; also excludes readers in rollback mode
```

Use `BEGIN IMMEDIATE` for a read-then-write unit. With deferred mode, an initial read starts a read
snapshot; a later write may fail with `SQLITE_BUSY` when it cannot upgrade. `IMMEDIATE` fails before
the work if another writer already exists.

On `SQLITE_BUSY` or `SQLITE_BUSY_SNAPSHOT`, roll back and retry the complete transaction with a
bounded policy unless the binding documents a safe narrower retry. Never loop forever. A busy
timeout waits for ordinary lock contention but cannot make long write transactions scalable.

Use savepoints for nested application units; `BEGIN` statements do not nest:

```sql
SAVEPOINT item;
-- work
ROLLBACK TO item;  -- on failure
RELEASE item;
```

## Choose rollback journal or WAL intentionally

| Mode | Use when | Costs and limits |
|---|---|---|
| Rollback journal | Default behavior is sufficient; maximum portability or simple quiescent copies matter | Writers and readers block one another during parts of commit |
| WAL | Readers must continue during writes and every process is on the same host | `-wal` and `-shm` are part of live state; still one writer; checkpoints need attention |

Enable WAL only after coordinating all users of the file:

```sql
PRAGMA journal_mode = WAL;
```

The returned value must be `wal`; a successful statement that returns another mode did not change
the database. WAL mode persists. Do not toggle journal modes while other processes hold the file,
and never use WAL over a network filesystem.

## Set durability from requirements

- `synchronous=FULL` provides stronger power-loss durability and is the conservative choice.
- In WAL mode, `synchronous=NORMAL` preserves database consistency but a recent committed
  transaction may be lost after an operating-system crash or power failure.
- `synchronous=OFF` can trade away integrity after failure. Do not use it for durable data.

Apply `synchronous` to every connection. Do not describe `NORMAL` as fully durable or carry a WAL
recommendation into rollback mode without re-evaluating the guarantees.

## Prevent WAL growth

Readers see a stable snapshot. A long-lived reader can prevent a checkpoint from advancing beyond
its end mark, so the WAL may grow even when writes are small. Close stale readers first; do not
delete the WAL file.

SQLite auto-checkpoints by default. For deliberate control, start with:

```sql
PRAGMA wal_checkpoint(PASSIVE);
```

Inspect the returned busy, log-page, and checkpointed-page counts. Use `RESTART` or `TRUNCATE` only
in an operational window where blocking and file-size changes are understood.

## Keep connection ownership explicit

Open a connection in the process that uses it. Never carry one across `fork()`, rename or unlink its
database while open, or let two threads use one connection concurrently unless the binding and
SQLite build explicitly serialize that use. Prefer one owner at a time even when a binding disables
its thread check.

Apply the connection contract in the pool's connection initializer. Size pools for actual reader
concurrency; extra idle connections consume memory and do not increase write throughput.
