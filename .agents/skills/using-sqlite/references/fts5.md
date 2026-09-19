# SQLite FTS5

## Choose FTS5 for full-text retrieval

Use FTS5 for token, phrase, prefix, and relevance search over substantial text. `LIKE '%term%'`
cannot use an ordinary prefix index. Confirm the deployed SQLite build includes FTS5 before making
it part of the schema.

Choose one storage model:

- A normal FTS5 table owns its indexed text and is simplest.
- An external-content table avoids a second stored copy of source columns but requires exact
  synchronization with the content table.
- A contentless table is specialized and cannot return stored column content. Do not choose it as a
  space optimization without understanding its update and delete restrictions.

## Keep external content synchronized

An external-content index needs insert, delete, and update triggers using the old values for token
removal:

```sql
CREATE VIRTUAL TABLE document_fts USING fts5(
    title,
    body,
    content='document',
    content_rowid='id'
);

CREATE TRIGGER document_ai AFTER INSERT ON document BEGIN
    INSERT INTO document_fts(rowid, title, body)
    VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER document_ad AFTER DELETE ON document BEGIN
    INSERT INTO document_fts(document_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
END;

CREATE TRIGGER document_au AFTER UPDATE ON document BEGIN
    INSERT INTO document_fts(document_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
    INSERT INTO document_fts(rowid, title, body)
    VALUES (new.id, new.title, new.body);
END;
```

Creating triggers does not index rows that already exist. Build the initial index after the table
and triggers exist:

```sql
INSERT INTO document_fts(document_fts) VALUES ('rebuild');
```

Do not use `INSERT OR REPLACE` as a substitute for the delete path on an external-content table.

## Treat MATCH as a query language

`MATCH` accepts phrases, Boolean operators, column filters, `NEAR`, and prefixes. Bound parameters
prevent SQL injection but do not turn FTS syntax into literal text. Either expose and validate a
documented search syntax or quote user text as an FTS phrase, doubling embedded double quotes.

```sql
SELECT d.id, d.title, document_fts.rank
FROM document_fts
JOIN document AS d ON d.id = document_fts.rowid
WHERE document_fts MATCH ?
ORDER BY document_fts.rank
LIMIT 20;
```

The default `rank` is based on `bm25()` and better matches sort first in ascending order. Add prefix
indexes only for prefix lengths the product actually uses; they increase database and write cost.

## Check and repair the index

For an external-content table, compare the index with the source content by passing rank `1`:

```sql
INSERT INTO document_fts(document_fts, rank) VALUES ('integrity-check', 1);
```

The check succeeds without rows or fails with an SQLite error. Do not query a result row from the
`INSERT`. When triggers were missing, existing content was never indexed, or the check reports
drift, rebuild from the source table:

```sql
INSERT INTO document_fts(document_fts) VALUES ('rebuild');
```

Use `optimize` after a large bulk load or when measured segment fragmentation warrants it, not on
every write:

```sql
INSERT INTO document_fts(document_fts) VALUES ('optimize');
```
