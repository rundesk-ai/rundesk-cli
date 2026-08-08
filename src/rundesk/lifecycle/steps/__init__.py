"""Install migration steps — one per file, found rather than listed.

A step is `NNNN_what_it_does.py` exposing one function:

    def carry(data: Path) -> None:
        \"\"\"One sentence saying what changed and which release changed it.\"\"\"

`data` is the install's `data/` directory, and it is the only thing the step is handed.

**Five rules, and none of them bends:**

1. **A step imports nothing of rundesk's.** Not `utils.files`, not `core.paths`, not `core.config` —
   nothing under this package, however obviously the right tool it is. A step written today runs on
   installs carried forward years from now, by code that has moved on and by a runner that loads it
   from a file rather than importing it, so anything it reaches for is a name that has to still exist
   and still mean the same thing on a machine nobody has in front of them. **This costs something and
   the cost is the point:** a step that moves files wants `utils.files.stage_copy` more than anything
   else in this product, and it copies in the few lines it needs instead. Its sibling pays the same
   price — the agent level's `0001` carries its own statement splitter rather than reaching for
   `utils.scripts` — and `tests/test_migration.py` reads every step here with `ast` and refuses one
   that reaches for this product, so the rule is checked rather than remembered.
2. **A shipped step is never renumbered, renamed, edited or back-filled.** Its id is how every install
   on every machine knows whether it has already run, and its *number* has to be above every number
   any previously shipped release used. A step that needs changing is a *new* step with a higher
   number. **Nothing can catch a broken one here, which is why this rule is the step author's to
   keep:** how far an install has been carried is a single id, so a step numbered below it never runs
   at all, on any install already past that mark, and nothing anywhere says so. The agent level keeps
   a row per step and can therefore ask the question — `agents.migration.Backfilled` refuses an agent
   whose rows say otherwise — and this level cannot even see it.
3. **A step is safe to run against an install that does not need it.** It may find the thing it was
   written to move already gone — an owner tidied it, or a half-finished run got that far. Check,
   then act; never assume the starting shape.
4. **A step may copy and may create, and deletes only what it has just replaced.** Losing what an
   owner keeps is the one failure a migration must never cause, and a step that cannot finish leaves
   both copies rather than neither.
5. **Nothing puts an install back, so a step is additive and idempotent throughout.** The mark is
   written *after* a step returns, so a step that dies partway is not recorded — and the next carry
   hands it its own half-finished work and runs it again from the top. `rundesk update` keeps a copy
   of `data/` before it carries, but only while the owner leaves `backup_enabled` on and only as
   something a person restores by hand afterwards: it is not a rollback and no step may be written
   expecting one. So write every step to land in the same place whether it runs once or is
   interrupted and run again. The agent level has a real rollback and needs this only inside the
   directories that rollback leaves out; here it is everywhere, for every step.

There are no steps yet. The first release to change the shape of an install adds the first one.
"""
