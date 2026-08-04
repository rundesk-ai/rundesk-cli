# Memory — rundesk-cli

Always-loaded, read at the start of every task: the friction we've hit in **this codebase** and the
workaround for each — so you don't re-hit it. **A living list — delete an entry once it's genuinely solved;
a long MEMORY means something was solved and never pruned.** This codebase only.

## Friction / gotchas

*One bullet each: the trap, and the workaround. Delete when it's genuinely solved.*

- **The owner's live install is a running product, not a fixture. Never touch it.** It stands at
  `~/.rundesk` and has real agents in it. Never install, uninstall, update, start, stop or write anything
  there, and never run a command that resolves there by default. Everything in the rebuilt tree resolves
  from **one** variable, `RUNDESK_HOME` — set it, or use `./dev`, which scrubs the whole `RUNDESK_*`
  namespace and *then* points that one variable at a scratch root. That ordering is the trap the previous
  build kept hitting: an override written in front of a scrubbing `env -u` prefix is taken away again by
  the scrubber, and the default wins silently. Check `ls ~/.rundesk` before and after anything that writes.

- **The `.knowledge/` payload is checksum-pinned, so editing a shipped standard fails the lint rather than
  saving your change.** `guides/docs-*.md`, `scripts/doc-lint` and `scripts/test_doc_lint.py` are hashed in
  `.payload-manifest` and re-hashed on every `doc-lint` run. They belong upstream in `knowledge-template`
  and arrive here as a version bump. `guides/README.md` and `scripts/README.md` are deliberately *not*
  pinned — those two are yours to extend.

- **A check that discovers what to run must fail when it discovers nothing.** The replaced build's gate and
  its CI both ran `glob('src/**/*.py')`; when the tree moved, both matched zero files and printed
  `parse OK`. A green check that ran nothing is worse than a red one. Anything here that finds its own work
  — suites, modules, verbs — asserts a non-empty result before reporting success.

---
*Editing this file? Follow the standard first: [`guides/docs-memory.md`](./guides/docs-memory.md).*
