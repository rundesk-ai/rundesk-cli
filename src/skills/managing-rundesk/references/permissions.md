# Machine permissions

What **macOS** lets this install do. Not what a brain's tool permissions allow, and not file
ownership: these are the operating system's own grants, such as Accessibility, Screen Recording, and
Full Disk Access.

## Commands

| Command | Control |
|---|---|
| `permissions` or `permissions list` | Report what the last check found. Runs nothing and touches nothing. |
| `permissions lineage` | Say whose grants an answer from this process would be about. |
| `permissions check` | Prove everything needed to operate the machine, and record what was found. |
| `permissions check <probe>` | Prove one group (`control`) or one probe (`files/full-disk`), leaving every other stored answer at its older timestamp. |
| `permissions check --everything` | Also prove the probes that are not needed to operate the machine. |
| `permissions check --verbose` | Also print what each program really said. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## An answer belongs to a process, not to a machine

macOS makes the nearest application bundle responsible for a permission. Anything started from a
terminal inherits what the owner once granted that terminal; a gateway is a launchd job with no
application above it and starts with nothing. The two disagree, and that is expected.

**Asking from inside a turn is not reliably asking as the gateway.** A `permissions check` run
through a brain's tool call can answer about that tool's program instead, because the tool leaves the
gateway shim out of the parent chain. Read the lineage line in the output rather than assuming the
invocation: only a run that says `gateway` is a fact about the gateway.

Report the lineage together with any verdict. A verdict without the process it was measured in is not
an answer the owner can act on.

## Reading the result

- A probe nobody has run reads `not checked`. That is not a denial; it is an absence.
- `unproven` counts as trouble: a check that proved nothing has proved nothing. Never report it as
  working.
- `check` exits `0` only when everything asked for is ready, so it can gate a script.
- `check` refuses to run at all when it cannot work out which lineage it is in. A table of verdicts
  with no process named is a claim about nobody.

## Safety

- Nothing here prompts, and nothing is left behind. Where no non-prompting way to ask exists, the
  probe answers `unproven` rather than guessing.
- One grant covers every agent on this machine: they are one client, not one each. The client is the
  interpreter, so upgrading it can take the grants away with no warning, and `check` is what finds
  out.
- Never tell the owner to grant a permission Rundesk does not need for the task at hand. Name the
  probe that failed and the one command that fixes it.
- Granting is the owner's action in System Settings. Report what is blocked; do not attempt to work
  around a denial.
