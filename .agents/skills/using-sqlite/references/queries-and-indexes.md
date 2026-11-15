# SQLite queries and indexes

## Keep data separate from SQL

Bind every runtime value with the host binding's positional or named parameters. Parameters cannot
represent a table name, column, collation, operator, or sort direction; choose those fragments from
an exact allowlist before composing SQL.

`LIKE` parameters are safe from injection but `%` and `_` still act as wildcards. If the user means
literal text, escape the escape character, `%`, and `_`, then declare the same escape character:

```sql
SELECT id, name
FROM item
WHERE name LIKE ? ESCAPE '\';
```

Do not forward raw input to FTS `MATCH`; it is its own query language. Use the FTS5 reference when
full-text search is required.

## Respect affinity and collation

Use compatible declared types and collations on both sides of joins and comparisons. SQLite may
coerce values according to column affinity, so a text identifier that merely looks numeric can
compare differently from an untyped expression.

The built-in `NOCASE` collation performs ASCII case folding, not general Unicode case-insensitive
comparison. For Unicode search, normalize into a dedicated column or install and consistently use a
tested collation. An index is usable for ordering and comparison only when its collation matches the
query.

## Read the plan, not just timing

Run the exact parameter shape against representative data:

```sql
EXPLAIN QUERY PLAN
SELECT id, created_at
FROM event
WHERE account_id = ? AND status = ?
ORDER BY created_at DESC
LIMIT 50;
```

`SEARCH ... USING INDEX` means the planner narrows rows through an index. `SCAN` means it visits all
entries in a table or index; that may be correct for a small table or a query returning most rows.
`USE TEMP B-TREE` for `ORDER BY`, `GROUP BY`, or `DISTINCT` identifies a sort an index might avoid.
Treat the textual plan as diagnostic output, not a stable machine-readable API.

## Build indexes from real query shapes

- Put equality-constrained columns first, then the range or ordering columns that follow them.
- A composite index supports its leftmost prefixes. Remove a shorter index that is a true prefix of
  a longer one unless measurement proves a separate need.
- Index foreign-key child columns in their declared order.
- Use a partial index when queries repeatedly select the same stable subset:

  ```sql
  CREATE INDEX job_ready_idx ON job(priority DESC, created_at)
  WHERE state = 'ready';
  ```

- Use an expression index only when the query repeats the same expression and collation:

  ```sql
  CREATE INDEX account_email_folded_idx ON account(lower(email));
  ```

- Add selected output columns to make a covering index only after proving table lookups matter.

Every index consumes disk and adds work to inserts, updates, deletes, migrations, backups, and WAL
checkpoints. Do not create one index per column or keep speculative indexes.

## Refresh planner statistics safely

Run `PRAGMA optimize` after schema changes and at the lifecycle point appropriate to the
application. Current SQLite versions bound the analysis work themselves. Use explicit `ANALYZE`
only when supporting an older runtime or when a measured plan problem requires deliberate control.

Re-run the plan and timing after adding or removing an index. If the plan does not change and the
workload does not improve, the index has not earned its write and storage cost.
