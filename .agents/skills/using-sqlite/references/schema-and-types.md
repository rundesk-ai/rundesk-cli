# SQLite schema and types

## Design for SQLite's type system

SQLite stores values as `NULL`, `INTEGER`, `REAL`, `TEXT`, or `BLOB`. In an ordinary table, a
declared column type selects an affinity; it does not reject every other storage class. A value that
looks numeric may be converted on insert or comparison.

Use `STRICT` tables when the supported runtime is SQLite 3.37 or newer and the application expects
rigid types:

```sql
CREATE TABLE account (
    id         INTEGER PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    enabled    INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    balance_cents INTEGER NOT NULL CHECK (balance_cents >= 0),
    created_at TEXT NOT NULL
) STRICT;
```

`STRICT` columns accept only `INT`, `INTEGER`, `REAL`, `TEXT`, `BLOB`, or `ANY`. They still apply
lossless coercion, so validate application-level formats separately. On older runtimes, combine
ordinary affinities with `NOT NULL`, `CHECK`, `UNIQUE`, and foreign keys.

## Store domain values deliberately

- Store booleans as `INTEGER` with `CHECK (value IN (0, 1))`; SQLite has no Boolean storage class.
- Store timestamps consistently as UTC ISO-8601 `TEXT`, Unix time `INTEGER`, or Julian day `REAL`.
  Do not mix encodings in one column, and document precision and timezone rules.
- Store exact money as an integer smallest unit. Binary `REAL` cannot exactly represent decimal
  currency.
- Do not expect `VARCHAR(40)` or `DECIMAL(10,2)` to enforce length or scale. Use `CHECK` constraints.
- Use `BLOB` only for opaque bytes. A field that must sort, filter, or join needs a deliberate
  comparable representation.

## Choose keys with SQLite's row model in mind

In an ordinary table, exactly `INTEGER PRIMARY KEY` aliases the 64-bit rowid and receives an
automatic value when omitted. `INT PRIMARY KEY` is a separate unique index and is not a rowid alias.

Avoid `AUTOINCREMENT` unless an identifier must never reuse any previously committed rowid. Normal
`INTEGER PRIMARY KEY` already generates unused values; `AUTOINCREMENT` adds writes and storage and
does not guarantee gap-free numbering.

Consider `WITHOUT ROWID` only for a non-integer or composite primary key after measuring. It makes
the declared primary key the table's storage key and enforces `NOT NULL` on every key column, but it
removes rowid APIs and can be worse for large rows. Prefer an ordinary table for a single integer
primary key.

Explicitly add `NOT NULL` to primary-key columns in ordinary, non-`STRICT` tables. SQLite preserves
a legacy behavior that otherwise allows `NULL` in many declared primary keys.

## Make invalid states unrepresentable

Use schema constraints for invariants that must survive every caller:

```sql
CREATE TABLE document (
    id        INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
    status    TEXT NOT NULL CHECK (status IN ('draft', 'published', 'archived')),
    title     TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    slug      TEXT,
    UNIQUE (account_id, slug)
) STRICT;

CREATE INDEX document_account_idx ON document(account_id);
```

Remember that `CHECK` passes when its expression is nonzero or `NULL`; pair it with `NOT NULL` when
`NULL` must fail. `UNIQUE` treats `NULL` values as distinct, so the example permits multiple rows
with a null slug. Use a partial unique index when uniqueness applies only to a subset.

## Enforce foreign keys completely

Enable `PRAGMA foreign_keys = ON` on every connection and verify it returns `1`. Parent columns must
be a primary key or match one `UNIQUE` constraint or index with the same column order and collation.
Index each child-key sequence so parent deletes and updates do not scan the child table.

Use explicit `ON DELETE` and `ON UPDATE` actions. Do not assume cascade. Run
`PRAGMA foreign_key_check` after bulk imports, restores, and table rebuilds; it reports one row per
violation and is separate from `integrity_check`.
