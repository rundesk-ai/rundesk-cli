# Using SQLite Validation

This is the current validation record for `using-sqlite`; the repository-wide method is in
[Validating Skills](../../../docs/guides/validation.md).

## Boundary under test

The skill should activate for applications storing data in SQLite — the embedded file lifecycle,
type affinity and strict tables, foreign-key enforcement, transactions, WAL and single-writer
behavior, integrity checks and backup, FTS5, lock contention, and filesystem constraints. It should
not activate for a client/server database or for engine-independent data modelling.

## Trigger and exclusion cases

| ID | Request shape | Expected behavior |
|---|---|---|
| SQL-T01 | Choose column types for a new SQLite table | Load |
| SQL-T02 | "Writes intermittently fail with 'database is locked'" | Load |
| SQL-T03 | Configure a PostgreSQL connection pool | Do not load |
| SQL-T04 | Normalize an entity model with no engine chosen | Do not load |
| SQL-T05 | Back up a SQLite database that is being written to | Load |
| SQL-T06 | A Python service storing state in SQLite | Compose with `using-python`; each owns its half |

## Workflow and authority cases

| ID | Request shape | Expected behavior |
|---|---|---|
| SQL-W01 | An integer stored in a `TEXT` column and comparisons behave oddly | Explain type affinity and offer `STRICT` tables, naming the version that introduced them |
| SQL-W02 | Foreign keys declared but not enforced | Identify that enforcement is off by default and must be enabled per connection |
| SQL-W03 | Concurrent writers assumed | State the single-writer model, offer WAL and a busy timeout, and say what WAL does not solve |
| SQL-W04 | The database file copied while the application runs | Reject it; require the backup API or a documented safe procedure |
| SQL-W05 | Strict tables or a version-gated feature proposed | Check the linked library version, not just the language binding |
| SQL-W06 | "Backups are working" | Reject fluent assurance; require a restore into a scratch path plus an integrity check |
| SQL-W07 | The SQLite library version cannot be determined | Query it or stop and name the unknown |
| SQL-W08 | The file lives on a network filesystem | Surface the locking limitation rather than tuning around the symptom |

## Provider evidence

Last verification: not yet run against a live provider matrix.

- Claude Code: pending. Cases marked for the sampled run are SQL-T01, SQL-T03, SQL-W06, and SQL-T06.
- Codex: not run.

No case below is marked passed. Record client versions, model identifiers, isolation constraints,
and per-case results here before claiming provider compatibility.

## Limits

SQL-T06 requires `using-python` in the same workspace. No case runs against a live filesystem under
contention; SQL-W03 and SQL-W08 are graded on the decision and the limitation named.
