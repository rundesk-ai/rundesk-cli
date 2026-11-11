# Compatibility and migrations

Reviewing a change that alters stored data or a published contract. The defects here are not visible
in the diff: they appear at deploy time, in the window between two versions running at once, or in a
consumer nobody listed.

## Establish who is on the other side

Before judging the change, name what depends on it. A compatibility review with no consumer
inventory is a guess.

- Other services, jobs, and scheduled work that read the changed table or call the changed endpoint.
- Clients you do not deploy: mobile builds, browser sessions with cached assets, partner
  integrations, webhooks.
- Data already written in the old shape, including backups, exports, caches, and queued payloads.
- Anything reading the database directly — reporting, analytics, admin tooling.

If the consumer set cannot be established, that is a finding. `Cannot conclude` is the honest verdict
when an unlisted consumer could break.

## Assume both versions run at once

Deployment is not atomic. Old and new code overlap — during a rolling deploy, on a queue holding
messages enqueued by the previous version, on a client that has not reloaded.

Ask of every change: **is the new code safe against old data, and is the old code safe against new
data?** Both directions must hold for the overlap window.

| Change in the diff | What breaks in the overlap |
|---|---|
| Column dropped or renamed in one migration | Old instances still select it and fail |
| Column added `NOT NULL` with no default | Old instances insert without it and fail |
| Enum value added | Old code hits an unmatched branch |
| Enum value removed | Old rows deserialize into nothing |
| Field removed from an API response | Clients still reading it break, including cached bundles |
| Queue payload shape changed | In-flight messages fail on the new consumer, or the reverse |
| Serialization format changed | Cached and persisted values from before the change fail to load |

The safe form is almost always **expand, migrate, contract**: add the new shape, write both, backfill,
move readers, and only then remove the old shape — as separate deploys, not one. A change that adds
and removes in a single step should be flagged unless the reviewer can show no overlap is possible.

## Read the migration as an operation, not a script

A migration that is correct can still take the site down.

- **Locking.** Does it hold a lock that blocks reads or writes, and for how long at production row
  counts? An `ALTER` that rewrites the table is a different operation at ten thousand rows and at a
  hundred million.
- **Duration and batching.** Is a backfill bounded and resumable, or one statement over the whole
  table? Long transactions hold locks and bloat.
- **Ordering against the deploy.** Does the migration run before or after the code that needs it, and
  is the sequence correct in both directions?
- **Reversibility.** Is there a down path, and does it lose data? "Irreversible" is acceptable when
  stated and accepted; it is a finding when nobody noticed.
- **Idempotence.** If it fails partway and is retried, does it resume cleanly or corrupt?

For a destructive step — dropping a column, deleting rows, rewriting values — check that the data is
recoverable, that the step is separated from the change that stopped using it, and that a gap exists
between the two deploys long enough to notice a problem.

## Judge the backfill separately from the schema

A backfill is a data-correctness change wearing a migration's clothes. Review it on its own terms:
what it computes, what it does to rows that are already correct, what it does to rows written while
it runs, and how anyone would know it finished correctly.

A backfill with no verification query is unproven work.

## Contracts break quietly

For a published interface, check that the change is additive, or that it is versioned and the
deprecation has a path. Adding a field is safe only if consumers tolerate unknown fields; adding an
enum value is safe only if consumers do not switch exhaustively on it.

Where a contract test or schema exists, check the change is reflected there — an interface change
with a green contract suite usually means the suite does not cover the changed part.

## Findings to look for specifically

- A migration and the code that depends on it in the same deploy, with no overlap analysis.
- A `NOT NULL` column added without a default or a backfill.
- A rename implemented as drop-plus-add.
- A destructive step with no stated recovery.
- A response field removed with no consumer inventory.
- A serialization or payload change with in-flight messages or cached values unconsidered.
- A backfill with no bound, no resumability, and no verification.

Each is reported the same way as any other finding: the trigger, the behavior, the impact, and the
missing safeguard. "This migration is risky" is not a finding; "old instances select this column for
the duration of the rolling deploy and will error" is.
