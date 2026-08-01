# Development

Craft rules for one bounded project change.

## Before you change anything

1. **Read the target first.** Read every governing instruction file the repository has —
   `AGENTS.md`, `CLAUDE.md`, whatever it names — before writing a line. Those rules beat habit.
2. **Name the outcome and how it will be proven.** If the brief did not say, decide and say what
   you decided.
3. **Look for what already exists.** A function, command or test that covers this beats new code.

## While you work

- **Only the authorized work.** Note anything else you spot in the report; do not fix it.
- **Preserve what you did not create.** The checkout may be dirty and none of it is yours. Never
  reset, stash, revert, force or discard.
- **Run the project's own tests and read the output.** A test you did not run proves nothing; a
  suite you skimmed is one you did not run.
- **Leave the checkout as you found it** apart from the authorized change.
- **Subagents get the same scope you have** and report back to you.

## The report

- **Outcome** — done, partly done, or blocked, in one line.
- **Changed** — every file, or the findings where nothing changed.
- **Verified** — the exact commands and what they said. Quote failures.
- **Risk** — what is uncertain, untested, or likely to bite.
- **Decisions needed** — what the parent agent must decide before this can be delivered.
