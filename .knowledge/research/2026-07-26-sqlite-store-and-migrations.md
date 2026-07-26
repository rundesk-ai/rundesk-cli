# Research: SQLite as a record store, and how the world orders migrations

**Last updated:** 2026-07-26
**Question it answers:** How does the world order and record schema migrations, and what does practice say about SQLite as a per-agent record store with a single query seam?

## What they do

There are two families, and almost nobody runs only one of them.

| | How steps are found | Ordered by | Recorded where | Backwards |
|---|---|---|---|---|
| **Alembic** | every file in `versions/` is read in on every run[7] | not the filename — a linked list. Each script carries `revision` and `down_revision`; the chain is composed "based on how the `down_revision` identifiers link together, with the `down_revision` of `None` representing the first file"[7] | `alembic_version`, created on first run, holding the current revision id[7] | a `downgrade()` per script, walked in reverse[7] |
| **Django** | a `migrations/` package inside each app, distributed with its code[9] | an explicit dependency **graph** — each `Migration` lists `dependencies`, including into other apps, so a `ForeignKey` forces the other app's migration to run first[9] | `django_migrations`[9] | `RunPython` takes a second callable; omit it and "migrating backwards will raise an exception". One irreversible operation makes the whole migration irreversible (`IrreversibleError`)[9] |
| **Rails** | `db/migrate/`, filenames of the form `YYYYMMDDHHMMSS_create_products.rb`[10] | the UTC timestamp in the filename — chosen over sequential integers so migrations written on two branches do not collide[10] | `schema_migrations`, one row per migration, the number in a `version` column[10] | `change` reverses itself where Active Record knows how; otherwise `up`/`down` or `reversible`, and a destructive step raises `ActiveRecord::IrreversibleMigration`[10] |
| **golang-migrate** | `{version}_{title}.up.sql` and `.down.sql` pairs[11] | a 64-bit unsigned integer: "All migrations are applied upward in order of increasing version number, and downward by decreasing version number." Sequence numbers or Unix timestamps both qualify — any distinct increasing integer[11] | a schema-migrations table it creates itself, carrying a **dirty** flag[12] | explicit `.down.sql` files[11] |
| **Flyway** | scripts discovered on configured locations[13] | version order[13] | a schema history table (name set by the `table` setting) — "a complete audit trail of all changes performed against the schema", recording which migrations applied, when, by whom, their checksums and whether they succeeded[13] | not covered by the page read[13] |
| **sqlite-utils / Beets** | **nothing is found — there is no file set.** The declared schema *is* the record[14][15] | n/a | n/a | n/a |

**The declarative family reconciles instead of stepping.** Beets diffs the model's declared fields against
the live table and emits one `ALTER TABLE` per missing column — for a table that already exists,
`setup_sql += f"ALTER TABLE {table} ADD COLUMN {name} {typ.sql};\n"` for each declared name not in
`current_fields`. There is no path that removes a column, so a retired field stays on disk forever.[15]
`sqlite-utils` splits the same problem in two: `add_column()` for what SQLite's `ALTER TABLE` can do, and
`transform()` for everything else, documented as six steps — start a transaction, `CREATE TABLE
tablename_new_x123` with the required changes, `INSERT INTO tablename_new_x123 SELECT * FROM tablename`,
`DROP TABLE tablename`, `ALTER TABLE tablename_new_x123 RENAME TO tablename`, commit — and described there
as the approach the SQLite documentation gives.[14]

SQLite's own page is where that comes from. `ALTER TABLE` does `RENAME`, `RENAME COLUMN`, `ADD COLUMN` and
`DROP COLUMN` and nothing else; an added column "may not have a PRIMARY KEY or UNIQUE constraint", and if
`NOT NULL` is specified "the column must have a default value other than NULL".[5] For anything beyond
that the docs give a 12-step generalized procedure and warn against the tempting shortcut: renaming the old
table out of the way first "might corrupt references to that table in triggers, views, and foreign key
constraints".[5]

**A failure halfway is answered by the database, not by the tool.** Django: "On databases that support DDL
transactions (SQLite and PostgreSQL), all migration operations will run inside a single transaction by
default. In contrast, if a database doesn't support DDL transactions (e.g. MySQL, Oracle) then all
operations will run without a transaction" — and for those, "MySQL lacks support for transactions around
schema alteration operations, meaning that if a migration fails to apply you will have to manually unpick
the changes in order to try again (it's impossible to roll back to an earlier point)."[9] Rails wraps each
migration in a transaction where DDL transactions exist, and where they do not, "the parts of it that have
succeeded will not be rolled back. You will have to rollback the changes manually."[10] Alembic runs the
whole series in one transaction unless `transaction_per_migration=True`, which "nest[s] each migration
script in a transaction rather than the full series of migrations to run".[8]

Where the database cannot help, the tool leaves a mark instead. golang-migrate: "Before a migration runs,
each database sets a dirty flag. Execution stops if a migration fails and the dirty state persists, which
prevents attempts to run more migrations on top of a failed migration" — and the operator "need[s] to
manually fix the error and then 'force' the expected version".[12] Flyway records success in the history
row and re-checksums every already-applied script on each run, erroring when one does not match, "usually a
result of migrations being edited after being applied to the database".[13]

**SQLite is on the transactional-DDL side of that line, which is easy to get wrong.** Django's docs name it
beside PostgreSQL.[9] Measured on SQLite 3.51.0 through the macOS stdlib binding: inside one
`BEGIN IMMEDIATE`, a `CREATE TABLE`, an `ALTER TABLE ... ADD COLUMN` and an `INSERT` all disappeared on
`ROLLBACK` — the table was gone, the column was gone, the row was gone. A `PRAGMA user_version = 99` in the
same transaction rolled back to its previous value too, so the version stamp is transactional with the DDL
it describes.[23]

**Backwards is where the field disagrees with itself.** Rails, Alembic and golang-migrate all ship a down
path; Django ships one that any single irreversible operation cancels for the whole migration.[7][9][10][11]
The case where the *data* is newer than the code has a different and blunter answer. Android's Room throws:
"If Room can't find a migration path to upgrade an existing database on a device to the current version, an
`IllegalStateException` occurs."[16] The only alternative it offers for a database whose version is higher
than the code's is `fallbackToDestructiveMigrationOnDowngrade()`, which recreates the tables and permanently
deletes what was in them.[16] Refuse, or destroy — those are the two shipped answers.

**What SQLite says about this shape.** WAL: "Readers do not block writers and a writer does not block
readers. Reading and writing can proceed concurrently", but "Since there is only one WAL file, there can
only be one writer at a time."[1] It is sticky — "If a process sets WAL mode, then closes and reopens the
database, the database will come back in WAL mode"; measured, a reopened file reported `wal` without being
asked.[1][23] It costs two extra files, "-wal" and "-shm", and one hard constraint: "All processes using a
database must be on the same host computer; WAL does not work over a network filesystem."[1] Checkpointing
happens automatically at a threshold of 1000 pages by default.[1] Durability is a separate dial: "WAL mode
is safe from corruption with synchronous=NORMAL" but "does lose durability" — a committed transaction
"might roll back following a power loss or system crash" — while `FULL` "is atomic, consistent, isolated,
and durable (ACID) in WAL mode".[3]

`BEGIN IMMEDIATE` versus the default: a DEFERRED transaction does not start until first access, and a later
write "upgrade[s] the transaction to write if possible, or return[s] `SQLITE_BUSY`", whereas IMMEDIATE
"starts a new write transaction immediately, without waiting for a write statement".[2] Measured with
`busy_timeout` at zero, a second `BEGIN IMMEDIATE` failed at once with `database is locked` while a reader
on the same file kept reading.[23] `PRAGMA busy_timeout` is documented as the binding-friendly alternative
to `sqlite3_busy_timeout()`, and "Each database connection can only have a single busy handler. This PRAGMA
sets the busy handler for the process, possibly overwriting any previously set busy handler."[3] SQLite's
own default is 0; Python's is not — `sqlite3.connect()` takes `timeout`, "Default five seconds", and sets
it, so a default Python connection reads `PRAGMA busy_timeout` as 5000 while one opened with `timeout=0`
reads 0.[6][23]

`PRAGMA user_version` "will get or set the value of the user-version integer at offset 60 in the database
header. The user-version is an integer that is available to applications to use however they want. **SQLite
makes no use of the user-version itself.**"[3] Its neighbour `schema_version`, at offset 40, is SQLite's own
and carries a warning: changing it "may cause SQL statement to run using an obsolete schema, which can lead
to incorrect answers and/or database corruption", and "Misuse of this pragma can result in database
corruption."[3]

FTS5 external content stores only the index and fetches column values back from the content table when it
needs them: "It is still the responsibility of the user to ensure that the contents of an external content
FTS5 table are kept up to date with the content table", by triggers.[4] The delete command must be handed
the row's *old* values — "If the values 'inserted' into the text columns as part of a 'delete' command are
not the same as those currently stored within the table, the results may be unpredictable ... This can
leave the full-text index in an unpredictable state, making future query results unreliable."[4] `'rebuild'`
discards the whole index and rebuilds it from the content table; `'optimize'` merges the b-trees and "can
take a long time to run".[4]

**The seam, as the field names it.** Repository "Mediates between the domain and data mapping layers using a
collection-like interface for accessing domain objects", "acting like an in-memory domain object
collection".[17] Data Mapper is "A layer of mappers that moves data between objects and a database while
keeping them independent of each other and the mapper itself" — the domain objects need no SQL and no
schema knowledge, and the mapper is unknown to them.[18] Neither says anything about closing a connection,
and that is where the leak lives: Python's own docs state that a `Connection` used as a context manager
commits or rolls back and nothing more — "The context manager neither implicitly opens a new transaction
nor closes the connection. If you need a closing context manager, consider using `contextlib.closing()`."[6]

**A sibling Python project already runs this exact shape**, one SQLite file per profile on a laptop, and it
is worth reading because both halves of the answer are visible in one repository.

*Declarative reconciliation, adopted deliberately.* `SCHEMA_SQL` is the source of truth; `_init_schema`
runs `executescript(SCHEMA_SQL)` and then `_reconcile_columns`, whose docstring says it "Follows the
Beets/sqlite-utils pattern: the CREATE TABLE definition in SCHEMA_SQL is the single source of truth for the
desired schema", diffing `PRAGMA table_info` against the declared columns and adding what is missing. "This
makes column additions a declarative operation — just add the column to SCHEMA_SQL and it appears on the
next startup. Version-gated migration blocks are no longer needed for ADD COLUMN." The stated reason is
error class, not convenience: it "eliminat[es] the version-gated migration chain for column additions,
making it impossible for reordered or inserted migrations to skip columns."[19]

*And a numbered chain kept anyway, for what reconciliation cannot express.* "The schema_version table is
retained for future data migrations (transforming existing rows) which cannot be handled declaratively."[19]
`SCHEMA_VERSION` is 23, held in a one-row `schema_version` table; `PRAGMA user_version` is not used anywhere
in the repository.[19] The FTS storage layout carries a *second*, independent number, because tying it to
the first would have frozen everything else: "DECOUPLED VERSIONING. Crucially, this does NOT hold back the
main schema_version ... future v24+ migrations land automatically for legacy-FTS users too. Only the FTS
*layout* waits for opt-in."[19]

*Two traps the reconciler produced.* Ordering: indexes that mention a reconciled column cannot live in
`SCHEMA_SQL`, because "SCHEMA_SQL above is run by sqlite executescript which would otherwise fail on legacy
DBs ('no such column: active')" — so they were moved into a separate `DEFERRED_INDEX_SQL` run afterwards.[19]
And fidelity: a column added by the reconciler can arrive without its declared default, so "the
reconciler-added `active` column can lack its NOT NULL DEFAULT 1 ... so INSERTs that omitted the column
wrote NULL and the `WHERE active = 1` transcript loaders hid the whole history." The repair for it "was
previously gated at `current_version < 12` which never re-ran for already-v12+ databases" — the version
gate is what kept the fix away from the databases that had the bug.[19]

*The write path.* `_execute_write` documents why IMMEDIATE and why jitter: "BEGIN IMMEDIATE acquires the WAL
write lock at transaction start (not at commit time), so lock contention surfaces immediately. On `database
is locked`, we release the Python lock, sleep a random 20-150ms, and retry — breaking the convoy pattern
that SQLite's built-in deterministic backoff creates." Up to 15 attempts; the connection is opened with
`timeout=1.0` because "application-level retry with random jitter handles contention instead of sitting in
SQLite's internal busy handler for up to 30s", and with `isolation_level=None` because the binding's
implicit transactions "conflict[] with our explicit BEGIN IMMEDIATE ... None = we manage transactions
ourselves". A passive checkpoint runs every 50 successful writes and an FTS `optimize` every 1000, because
one segment per insert left unmerged "lengthens the write-lock hold time and starves competing writers
(gateway + cron processes share one state.db), surfacing as 'database is locked'."[19]

The same two ideas exist in 49 lines for the small stores: `add_column_if_missing`, which swallows
`duplicate column name` because a concurrent migrator may have won, and `write_txn` — "An IMMEDIATE write
transaction: at most one concurrent writer wins. The explicit ROLLBACK is guarded so a SQLite auto-rollback
(no active transaction left under EIO / lock contention / corruption) cannot shadow the original exception
with a spurious rollback error."[20]

*WAL is asked for, not assumed.* `apply_wal_with_fallback` probes the current mode read-only first —
"Read-only probe — no flock, no checkpoint, no WAL/SHM unlink. Skipping the set-pragma prevents WAL-init
from unlinking files other connections hold open" — falls back to `DELETE` when the filesystem answers
`locking protocol` (NFS, SMB, some FUSE), warns once per database label, and "Never downgrades to DELETE if
the on-disk DB header reports WAL", because a live downgrade under concurrent openers is worse than the
problem.[19]

*The FTS hazard sqlite.org documents, met head-on.* While a background rebuild is pending, two marker rows
define membership — "A row is indexed iff `id <= P` (backfilled) OR `id > H` (inserted after the drop; ids
are AUTOINCREMENT so new rows are always > H and the insert triggers index them live)" — and every trigger
gates on that same predicate, because "firing an FTS5 external-content 'delete' for a row that is NOT in
the index corrupts the index, and skipping it for a row that IS indexed leaves a stale entry."[19] When no
rebuild is pending both markers are absent and `COALESCE` turns the predicate into a tautology.[19]

*The cleanest seam in that repository is 230 lines and leaked file descriptors.* `cron/executions.py`
exposes module-level domain verbs — `create_execution`, `mark_execution_running`, `finish_execution`,
`recover_interrupted_executions`, `list_executions`, `latest_executions` — keeps `_connect()` private, lets
no SQL out, and returns plain dicts; the schema is created on connect with `CREATE TABLE IF NOT EXISTS` plus
two `CREATE INDEX IF NOT EXISTS` and carries no version number at all.[21] Every verb is written
`with _lock, _connect() as conn:`, and that is the defect: the report on the sibling issue says the pattern
"transmite uma falsa impressão de gerenciamento completo do recurso" — it conveys a false impression of
complete resource management — because "A transação termina, mas o lifecycle da conexão não termina de
forma determinística."[22] In WAL each surviving connection holds descriptors for the main file, the `-wal`
and the `-shm`; a long-lived process reaches `RLIMIT_NOFILE` and then fails with `[Errno 24] Too many open
files` in components that have nothing to do with the database.[22] One issue covered 21 call sites across
three ledgers, and the report lists six sibling issues of the same class, concluding they "demonstram padrão
recorrente: uso de context manager transacional interpretado incorretamente como gerenciamento completo da
conexão."[22] Its recommended fix is a local `_transaction()` per module that wraps `with conn:` in a
`try/finally: conn.close()`, explicitly *not* a shared global helper, plus a documentation line saying that
the `sqlite3.Connection` context manager does not close the connection.[22]

## What we can borrow

- **Two mechanisms, and be honest that it is two.** A declarative reconcile for additive schema, and a
  numbered chain for everything a reconcile cannot express — moving files, rewriting rows, splitting a
  column. The sibling project arrived at exactly that split after starting with only the chain.[19]
- **`PRAGMA user_version` is the right home for the number.** No table, no row, no query, no join, and it
  commits inside the same transaction as the DDL it describes.[3][23] The sibling project keeps a one-row
  `schema_version` table and gets nothing from it that the header would not have given.[19]
- **Find the steps, do not list them.** Alembic reads the whole directory; Django walks a graph. This is the
  same rule `AGENTS.md` already states about reading the surface off the parser — a hand-kept tuple of
  migration callables is a list written twice.
- **A plain increasing integer is enough here.** Rails' timestamps exist to stop two branches colliding, and
  golang-migrate asks only for "distinct, incrementing integers".[10][11] One repository, one release train,
  one machine: the integer wins on legibility.
- **`BEGIN IMMEDIATE` for every write, never DEFERRED.** A deferred transaction that discovers it needs the
  write lock halfway is a `SQLITE_BUSY` at the worst possible moment.[2][19]
- **Set `busy_timeout` explicitly, and retry with jitter above it.** Five seconds is an accident of the
  Python binding, not a decision, and deterministic backoff produces convoys.[6][19][23]
- **`contextlib.closing`, always, and the connection's owner is whoever opened it.** Python's docs name the
  fix; the sibling repository is the proof of what happens without it.[6][22]
- **The seam is a module of domain verbs, not a class with a `.conn`.** `cron/executions.py` is the shape:
  named questions in, dicts out, nothing about SQLite crossing the line.[21] It reads exactly like the
  Repository definition without importing the vocabulary.[17]
- **Read and write told apart at the seam, not by convention** — the roadmap already requires it, and WAL
  makes it cheap: readers do not block the one writer.[1]
- **Schema-on-connect is legitimate for a tiny store.** `CREATE TABLE IF NOT EXISTS` on every open removes
  the migration question entirely for something that only ever grows columns; it costs DDL on each open.[21]
- **If search lands, external-content FTS5 with triggers, and treat `'rebuild'` as the documented recovery
  rather than a repair we invent.**[4][19]
- **Refuse forward.** Room's default on an unknown version is to throw; its only alternative deletes the
  data.[16] Throwing is the behaviour the roadmap already wants for a version rundesk does not recognise.

## What to avoid

- **Never gate a repair on a version number.** The sibling project's `active IS NULL` heal was gated at
  `current_version < 12` and therefore never ran on the databases that had the bug; it had to be made
  unconditional.[19] A repair runs every open or it does not exist.
- **Never let a connection out of the seam** — not as a return value, not as a yielded object, not "just for
  the test". Twenty-one call sites in one issue is what that costs when nobody notices for a year.[22]
- **Never read `with conn:` as "closed".** It commits or rolls back and does nothing else, and the shape is
  so plausible that six separate issues in one repository are the same mistake.[6][22]
- **Do not `ADD COLUMN ... NOT NULL` in a reconcile.** SQLite refuses `NOT NULL` without a non-NULL
  default[5], and the sibling reconciler swallowed that failure at DEBUG level and shipped a column whose
  rows were silently NULL.[19]
- **Do not write a down-migration we will never run.** Django's own answer is that one irreversible
  operation makes the whole thing irreversible[9]; a `down()` that has never been executed is a comment.
- **Do not enable WAL unconditionally.** It is a laptop, and a laptop's home directory can be on iCloud
  Drive, Dropbox or an SMB mount — where "WAL does not work over a network filesystem"[1] and the sibling
  project needed a probe, a fallback and a rule against live-downgrading a file others hold open.[19]
- **Do not let FTS triggers fire against rows the index does not contain.** The docs say the index goes into
  "an unpredictable state"[4]; the sibling project needed two marker rows and a predicate on every trigger
  to stay out of it.[19]
- **Do not grow one 9962-line store module.** That is what the sibling `hermes_state.py` became; the 49-line
  shared-primitives file beside it is the part that reads well.[19][20]
- **Do not settle any of this ourselves.** Schema, stored data and migrations are a hard gate in `AGENTS.md`
  and an owner decision the roadmap already enumerates.

## Verdict for us

**The world's answer to "found or listed" is unanimous and we take it: found.** Migrations are files named
for the version they bring data up to, discovered by reading the directory, ordered by a plain integer,
executed in order and recorded once each — the ROADMAP's 4B behaviour, now with prior art behind every
clause. Nothing about the graph machinery in Alembic or Django transfers: those exist for many authors on
many branches against one shared database, and this is one repository shipping one release train.

**Where the number lives, we differ from the sibling project on purpose.** `rundesk.json` holds the layout
version, because a migration here can move files as well as columns and no in-database counter can describe
that; each `state.db` mirrors it in `PRAGMA user_version`, which is free, needs no table, and — measured —
commits and rolls back with the DDL it stamps.[3][23] The one-row `schema_version` table the sibling keeps
buys nothing we need.[19]

**Two mechanisms, and the split stated in the draft rather than discovered later.** Additive columns are
declarative — declared once in the schema and reconciled on open — because that is the class of change that
version-gated chains get wrong by skipping.[19] Everything else is a numbered step. What we do **not** take
from the declarative family is silence on failure: a reconcile that cannot add a column stops, it does not
log at DEBUG and carry on.[19]

**A failure halfway is cheap here and we should spend the whole of it.** SQLite has transactional DDL —
measured, `CREATE TABLE`, `ADD COLUMN`, the rows and the version stamp all roll back together[23] — so a
migration is one transaction, the version moves inside it, and there is no dirty flag to invent because
there is no half-applied state to record.[9][12] What remains is the file half of a migration, which is not
transactional; that is where "nothing is migrated in place until it has somewhere to fall back to" earns
its place, and it is the part the draft has to specify.

**Backwards: we write none, and we refuse forward.** Room's two shipped answers are throw or destroy[16];
destroying an owner's history is not on the table, so a `state.db` whose `user_version` is higher than this
rundesk is refused outright and the gateway stays down with the reason said. That matches 4B already, and
it is what makes down-migrations unnecessary rather than merely absent — the previous release is reached by
restoring what the migration kept, not by running code backwards.

**The seam: a module of domain verbs, and the connection never leaves it.** `cron/executions.py` is the
model to copy for shape[21] and the cautionary tale for lifecycle[22] — the same file is both. Concretely:
`BEGIN IMMEDIATE` for every write[2], `busy_timeout` set explicitly with jittered application-level
retry above it[19][23], `isolation_level=None` so the binding does not open transactions we did not ask
for[6][19], `contextlib.closing` at every boundary[6], reads and writes told apart at the seam, and no
`sqlite3` symbol importable outside the one module.

**Deferred, not refused:** FTS5. The external-content design with triggers is what we would build[4], and
the sibling project's high-water gating is the proof it needs real care[19]; it stays out of the first
schema, behind the `doctor`-reported capability check the roadmap already specifies, because it is a
compile-time option and the floor is the oldest Python a fresh macOS ships. **Not doing:** a shared
migration framework, a dependency-graph orderer, and any `down()`.

This feeds the ROADMAP phase 4 deliverables — the draft contract for the shape and the draft contract for
moving between versions — and, once ratified, the `agent-` component alongside `agent-run`, whose R-RUN-4
and R-RUN-5 already promise an append-only account that a row store has to keep promising.

## Open questions

- Whether `user_version` mirroring `rundesk.json` can ever disagree, and which one wins when a `state.db` is
  copied to a machine at a different version.
- Whether the reconcile runs on every open or only when `user_version` is behind — the sibling project's
  bug argues for every open, the cost argues against it.
- What a migration does with the raw files a run references, given the roadmap allows them to be destroyed
  and a migration cannot recreate one.
- Whether one write connection per gateway or one per operation is right, given the gateway is long-lived
  and the file-descriptor evidence is entirely about per-operation connections that were never closed.[22]
- Whether `synchronous=NORMAL` is acceptable for a record store on a laptop, given WAL loses durability
  across power loss at that setting but not atomicity.[3]
- What "the previous release is reached by restoring what the migration kept" actually means as a command,
  and whether the owner ever sees it.
- Whether the FTS capability check belongs in `doctor` alone or also in the seam, so a query that cannot be
  answered says so rather than returning nothing.

## Sources

1. SQLite, Write-Ahead Logging — https://www.sqlite.org/wal.html
2. SQLite, BEGIN TRANSACTION (DEFERRED / IMMEDIATE / EXCLUSIVE) — https://www.sqlite.org/lang_transaction.html
3. SQLite, PRAGMA statements (`busy_timeout`, `user_version`, `schema_version`, `synchronous`) — https://www.sqlite.org/pragma.html
4. SQLite, FTS5 (external content tables, `'delete'`, `'rebuild'`, `'optimize'`) — https://www.sqlite.org/fts5.html
5. SQLite, ALTER TABLE and the 12-step schema-change procedure — https://www.sqlite.org/lang_altertable.html
6. Python, `sqlite3` — connection context manager, `timeout`, `isolation_level` — https://docs.python.org/3/library/sqlite3.html
7. Alembic, Tutorial — `versions/`, `down_revision`, `alembic_version` — https://alembic.sqlalchemy.org/en/latest/tutorial.html
8. Alembic, Runtime API — `EnvironmentContext.configure(transaction_per_migration, version_table)` — https://alembic.sqlalchemy.org/en/latest/api/runtime.html
9. Django, Migrations topic guide — https://docs.djangoproject.com/en/5.2/topics/migrations/
10. Ruby on Rails, Active Record Migrations — https://guides.rubyonrails.org/active_record_migrations.html
11. golang-migrate, `MIGRATIONS.md` — https://github.com/golang-migrate/migrate/blob/master/MIGRATIONS.md
12. golang-migrate, `FAQ.md` — the dirty flag — https://github.com/golang-migrate/migrate/blob/master/FAQ.md
13. Redgate, Flyway schema history table — https://documentation.red-gate.com/fd/flyway-schema-history-table-273973417.html
14. `sqlite-utils`, Python API docs — `transform()` and `add_column()` — https://raw.githubusercontent.com/simonw/sqlite-utils/main/docs/python-api.rst
15. beets, `beets/dbcore/db.py` — `Database._make_table` — https://raw.githubusercontent.com/beetbox/beets/master/beets/dbcore/db.py
16. Android, Migrate your Room database — https://developer.android.com/training/data-storage/room/migrating-db-versions
17. Martin Fowler, P of EAA catalog — Repository — https://martinfowler.com/eaaCatalog/repository.html
18. Martin Fowler, P of EAA catalog — Data Mapper — https://martinfowler.com/eaaCatalog/dataMapper.html
19. Sibling project `hermes-agent`, `hermes_state.py` — `SCHEMA_SQL`, `_init_schema`, `_reconcile_columns`, `_execute_write`, `apply_wal_with_fallback`, the FTS high-water triggers, read 2026-07-26 — (internal)
20. Sibling project `hermes-agent`, `hermes_cli/sqlite_util.py` — `add_column_if_missing`, `write_txn`, read 2026-07-26 — (internal)
21. Sibling project `hermes-agent`, `cron/executions.py` — the domain-verb seam and schema-on-connect, read 2026-07-26 — (internal)
22. Sibling project `hermes-agent`, `relatorio-issue-69678-sqlite-fd-leaks.md` — the `with conn:` file-descriptor leak, read 2026-07-26 — (internal)
23. Probe of SQLite 3.51.0 through the macOS stdlib `sqlite3` binding, 2026-07-26 — DDL and `user_version` rollback, WAL persistence, `busy_timeout` defaults, `BEGIN IMMEDIATE` contention — (internal)
