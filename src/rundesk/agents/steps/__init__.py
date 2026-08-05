"""Agent migration steps — one per file, found rather than listed.

A step is `NNNN_what_it_does.py` exposing one function:

    def carry(conn: sqlite3.Connection, where: Path) -> None:
        \"\"\"One sentence saying what changed and which release changed it.\"\"\"

`conn` is an open connection to that one agent's records, **already inside `BEGIN IMMEDIATE`**, and
`where` is that agent's own directory. Both, because a step may need to change the tables and the
files together — and getting one without the other is how a schema that says a file is there ships
alongside a directory where it is not.

**Transactional DDL is real here**, and it is what the whole shape rests on. Measured through the
macOS binding on SQLite 3.51.0: a schema change, the rows it moved and the `migrations` row that
records the step all commit together or all go back together. There is no half-applied state to
detect and no dirty flag to keep — the row landing in the same transaction as the work is the whole
of the mechanism.

**Five rules, and none of them bends:**

1. **A step may never call `Connection.executescript()`.** It issues an implicit `COMMIT` before it
   runs, which silently drops the transaction the runner opened around it — so the step's work and
   the row that records the step stop being one thing, and a failure halfway leaves an agent
   changed and unstamped. Statements go one at a time, through `conn.execute`.

   **And a step may not split its SQL on `;` either**, which is the obvious replacement and is the
   same trap one step further on: a trigger body contains semicolons, so a step that adds one would
   hand `execute` half a trigger. Accumulate lines and run a statement when
   `sqlite3.complete_statement()` says it is one — that is the parser's own answer rather than a
   guess about its grammar. Step `0001` has it written out.
2. **A step may not import anything of rundesk's.** It has to go on working when the modules around
   it change under it: a step written today runs on an agent carried forward years from now, by
   code that has moved on and by a runner that loads it from a file rather than importing it. Step
   `0001` in particular carries everything it needs itself.
3. **A shipped step is never renumbered, renamed or edited.** Its id is how every agent on every
   machine knows whether that step has already run. A step that needs changing is a *new* step.
4. **A step is safe to run against an agent that does not need it.** It may find what it was
   written to change already there, or already gone. Check, then act; never assume the shape it
   starts from.
5. **A step may create and may copy, and deletes only what it has just replaced.** Losing what an
   agent has kept is the one failure a migration must never cause.

## Rebuilding a table, which is where the next step author will get hurt

Both of these were measured, both are silent when they go wrong, and neither is discoverable from
the SQLite documentation somebody would reach for.

**`PRAGMA foreign_keys=OFF` is a no-op inside a transaction — and still answers `1` when you ask
it.** SQLite's own documented twelve-step table-rebuild procedure *begins* by turning foreign keys
off, so **that procedure cannot be followed here at all**: a step is handed a live transaction, and
the first instruction silently does nothing while reporting that it worked.

What was proven to work instead, in this order: create the new table under a new name, copy the rows
into it, `DROP TABLE` the old one, `ALTER TABLE … RENAME TO` the old name, put back by hand every
reference that pointed at it, and then run `PRAGMA foreign_key_check`. That last one **returns rows
rather than raising**, so a step that runs it and ignores what comes back has checked nothing — read
the result and raise on it yourself.

**`DROP TABLE` fires the foreign-key actions that point *at* the table**, exactly as though an
implicit `DELETE FROM` had run first. So rebuilding a parent table silently empties every
`ON DELETE SET NULL` child: the rebuild reads as perfect, nothing raises anywhere, and the thing the
clause existed to preserve is gone. Whatever a rebuild is going to break has to be put back by the
same step, in the same transaction.

The first step is `0001`, which is what makes a directory an agent at all.
"""
