# requirements/

What Rundesk must do, and whether anything proves it.

A file here asserts and cites. It does not explain how something is built — that is the subsystem's
topic page — and it does not argue for the design. Every file takes the same closed shape:
`id`/`name`/`last_verified` frontmatter, then `What this is`, `Why it exists`, `Requirements`, and
`Open questions`, in that order and with nothing else.

| Contract | What it owns |
|---|---|
| [agent-delegation.md](./agent-delegation.md) | One agent's ask of another, and the answer it returns |
| [channel-adapter.md](./channel-adapter.md) | The seam a channel adapter is reached through |
| [channel-messaging.md](./channel-messaging.md) | A channel conversation, and the work that arrives on it |
| [channel-discord.md](./channel-discord.md) | Discord, as an agent is reached on it |
| [channel-slack.md](./channel-slack.md) | Slack, as an agent is reached on it |
| [provider-account-alias.md](./provider-account-alias.md) | Additional provider accounts, and the alias that selects one |
| [rundesk-instructions.md](./rundesk-instructions.md) | What every turn is told, and who owns each layer of it |
| [schedule-notification-target.md](./schedule-notification-target.md) | The one destination a schedule reports to |
| [team-catalog.md](./team-catalog.md) | Versioned agent teams, and what an install owes their declaration |

## The glyph is the whole point

The first column has no header and takes one of two values.

- **✅** — a named check was observed to pass, and the evidence cell names it.
- **❌** — everything else: unbuilt, built and untested, or covered by something nobody has run.

**A source path is not evidence, and neither is a test that merely exists.** The claim a ✅ makes is
that somebody watched it pass. Where that cannot be done the row stays ❌ with the reason, because a
visible gap is safe and a ✅ that quietly stopped being true is not. There is no third glyph;
"partly" is two rows.

## Identifiers

`R-<NS>-<n>`, with the namespace declared once in the frontmatter. One namespace per file, one file
per namespace, and an ID is never reused.

**Four numbers are missing** — `R-CAD-16`, `R-DIS-18`, `R-CH-22`, and `R-CH-27` — from requirements
withdrawn before this pass. They are deliberately not closed up. `R-CH-*` and `R-DIS-*` are cited in
shipped source and in test docstrings, so renumbering to close a gap would silently repoint every one
of those citations at a different requirement, and nothing would fail. A gap costs a reader one
question; a renumbering costs them a confident wrong answer.

## Authority

The product owner decides what Rundesk must do. Code, tests, documentation, and research establish
what is true and what is possible; they do not silently redefine what is wanted. Where they conflict
with a requirement, the conflict is recorded in `Open questions` and the owner decides which side
moves.

Three predecessor contracts were removed on 2026-08-25 — the previous build's role-worker design, its
Slack behavior, and its machine-permissions draft. Their requirement namespaces were cited nowhere
else, and [`concepts/permissions.md`](../concepts/permissions.md) remains the source of truth for
what macOS lets Rundesk do. Git history holds them.

**`SLK` is the one of those three that has been reissued.** The rebuilt Slack adapter took the
namespace back on 2026-09-02 and numbers from `R-SLK-1` again. That is safe here and would not be in
general: nothing in the tree cited a withdrawn `R-SLK-*` row, which was checked before it was
reissued. `ROL` and `DEL` stay withdrawn.
