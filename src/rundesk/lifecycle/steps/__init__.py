"""Install migration steps — one per file, found rather than listed.

A step is `NNNN_what_it_does.py` exposing one function:

    def carry(data: Path) -> None:
        \"\"\"One sentence saying what changed and which release changed it.\"\"\"

`data` is the install's `data/` directory. The step is handed nothing else, so it cannot quietly
depend on the rest of the product — which matters, because a step written today runs on installs
carried forward years from now by code that has moved on.

**Three rules, and none of them bends:**

1. **A shipped step is never renumbered, renamed or edited.** Its id is how every install on every
   machine knows whether it has already run. A step that needs changing is a *new* step.
2. **A step is safe to run against an install that does not need it.** It may find the thing it was
   written to move already gone — an owner tidied it, or a half-finished run got that far. Check,
   then act; never assume the starting shape.
3. **A step may copy and may create, and deletes only what it has just replaced.** Losing what an
   owner keeps is the one failure a migration must never cause, and a step that cannot finish leaves
   both copies rather than neither.

There are no steps yet. The first release to change the shape of an install adds the first one.
"""
