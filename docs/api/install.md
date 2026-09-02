# The install itself

| Command | Does |
|---|---|
| `status` | the version, where the install is, and every configured value |
| `version` | the version, and whether it is out of date |
| `install [--source <dir>] [--bin-dir <dir>]` | what `install.sh` runs |
| `update [--continue]` | move to the newest release, or say it is up to date |
| `uninstall --confirm [--purge]` | remove rundesk; `--purge` also takes the data |

`status` and `version` take no flags. `--continue` is for a channel conversation waiting on the
result, not for a person at a terminal.

## status

Answers *how rundesk is*. Takes no flags.

```console
$ rundesk status
WHAT              IS
version           <version>
home              /Users/you/.rundesk
program           /Users/you/.rundesk/app (installed)
data              /Users/you/.rundesk/data
backups           /Users/you/.rundesk/backups
secrets           /Users/you/.rundesk/data/secrets
projects          /Users/you/.rundesk/projects
agents            /Users/you/.rundesk/data/agents — 2 agents
fit to run        yes
backup_enabled    yes
backup_retention  7
command_link      /Users/you/.local/bin/rundesk
last_updated_at   2026-08-04T20:48:04Z
migration         nothing to carry — this release ships no migration steps
update_enabled    yes
update_time       03:00
automatic update  scheduled daily at 03:00 local time
```

`last_updated_at` is when a version last actually arrived — the install, or an update that really
moved. A run of `update` that finds nothing newer does not touch it, so the answer does not drift to
"just now" every time you check. Which version that was is `rundesk version`, so it is not repeated
here.

`agents` is where they stand and how many there are, in one row rather than two — the count is only
ever *of* that directory. A root nothing has been installed into, an install nobody has added an
agent to, and an agents directory that cannot be read are three different answers and not one.
Which agents they are is `rundesk agents`, so the names are not repeated here.

`program` says which copy of the code answered and whether it is this root's own install or a
checkout — running a checkout against an install's data is an ordinary thing to do by accident, and
this is where you see it. Exits non-zero when rundesk cannot run here.

## version

Reports the version and checks whether a newer one has been published. The check is not optional:
the reason anybody asks a program its version is to find out whether it is the one they should be
running.

```console
$ rundesk version
rundesk <version>
        <version>: UP TO DATE
```

**Being unable to ask is never reported as being up to date.** If GitHub cannot be reached the line
says `UNKNOWN` and goes to stderr, so it cannot be mistaken for the answer. The command still exits
`0`, because the question asked — what version is this — was answered from the machine itself.

## install

What `install.sh` runs after it has fetched a copy. Usable by hand from a checkout:

```sh
./rundesk install --bin-dir ~/.local/bin
```

When the selected root already has an installed program and any gateway is online or cannot be
proved offline, installation does not replace `app/` itself. It runs that installed program's
guarded `update` command instead. Active turns or schedules therefore queue the work; once the
install is quiet, the updater gracefully stands down every online gateway, replaces and settles
the program, and restores exactly those gateways. This also means an unpublished checkout is not
installed over live gateways: stop them first when that local replacement is genuinely intended.

The bootstrap installer takes no install arguments. Its only options are `-h` and `--help`; either
prints its usage and exits successfully before finding Python, fetching, or changing anything. This
is the safe way to inspect it:

```sh
./install.sh --help
```

Every other argument is refused with usage and exit code `2` before any install work begins.
`RUNDESK_HOME` selects the install root and `RUNDESK_BIN_DIR` selects where the command is linked.
Removal remains a command of the installed program:
`rundesk uninstall --confirm [--purge --root <dir>]`.

It places the program, lays down the directories and their notes, writes or fills in the
configuration, carries the migrations, reconciles the daily update job, links the command, and then **proves the installed command
answers** — an installer that reports success without checking has told somebody their machine is
ready when it is not.

It proves it with `status` rather than `version`, so the proof is answerable from the machine alone.
`version` asks GitHub, and an install that fails because GitHub is slow has reported a failure it did
not earn — the mirror of the mistake this whole command is built to avoid. `status` also refuses when
the interpreter behind the link is too old, which is exactly the install that looks finished and
cannot run.

## update

Moves this install to the newest published release, or says it is already on it.

```console
$ rundesk update
<version>: OUT OF DATE — v<newer> is available, run: rundesk update
        installing v<newer>
rundesk updated to v<newer>
        what changed: https://github.com/rundesk-ai/rundesk-cli/releases/tag/v<newer>
        application: updated to v<newer>
        ordinary catalogs: checked
        team catalogs: checked
```

A run whose application settles reports three distinct outcomes: application, ordinary catalogs,
and team catalogs. The daily coordinator records the same three outcomes in its automatic-update
log. A catalog failure is printed and logged against its own surface without hiding successful
independent work.

### `--continue`, and who it is for

With no flag, the command keeps the existing lifecycle below and never creates continuation work.
`--continue` is an explicit opt-in available only to one unambiguous active channel provider turn.
If owner guidance has joined that still-active turn, its latest message is the exact origin; the
turn does not become ambiguous merely because it was steered. The command records a compact durable
handoff before the existing queued worker starts. Once the update
reaches a truthful terminal result and that same agent's gateway and exact channel are healthy, one
new turn wakes the exact conversation. An already-current update does not needlessly require a new
gateway pid; a real restart does. A newer owner message, a newer turn, duplicate/crash claim, or
already delivered continuation suppresses another turn. The exact provider session resumes only
when its provider remains configured, supports resume, is still available, and the current
person-facing preface exactly matches the originating instruction fingerprint. A missing session,
changed provider, unsupported resume, or changed rules, access, or team authority starts a fresh
session under current rules instead of suppressing the requested wake or carrying stale authority.
Once admitted, the continuation emits the ordinary working and terminal channel states, so an
adapter restarted by the lifecycle resumes its activity indicator and always stops it when the turn
settles. A suppressed or busy continuation emits neither state.

The continuation prompt is Rundesk's lifecycle result, not a copied prompt or a synthesized owner
message. It tells a fresh session the exact `messages` command for recovering the recorded request
and progress, then tells the agent to verify the outcome and continue the first unfinished
objective. It is admitted directly rather than through `rundesk ask` or delegation. The handoff stores local
database ids, bounded lifecycle outcomes, and observed version/pid only—not owner text, provider
session handles, channel/person ids, credentials, agent names, or paths.

### The order, and what a busy install does instead

The update order is chosen so the failure that cannot damage anything happens first: ask,
then fetch to a temporary directory, stand down every online gateway, then swap and settle. The swap
stages every entry and renames them into place, putting back what was there if any part fails — so an
interrupted update leaves the install on the release it was, never on neither. Gateways that were
already offline remain offline; every gateway the update stopped is started again by the release
that landed, never by the updater's cached old job logic. A foreground gateway whose name launchd
cannot supervise must be stopped in its terminal first, because an unattended update cannot restore
it and will not take it offline permanently.

If a provider turn or schedule is active, a manual update is recorded durably and returns without
fetching or stopping anything. A detached install-level worker waits for the install to become
quiet, closes new-work admission, and then runs the ordinary update transaction. The worker has no
live provider environment, so infrastructure work never appears as activity inside a DM. An opted-in
request carries only its agent-local handoff identity; the worker never synthesizes a caller. Losing
the worker does not lose the request: the daily coordinator sees the same
`queued-update.json` and retries it. A failed attempt remains owned by the detached worker and is
retried with a hold-off for ordinary requests. An opted-in failure is terminal, records a truthful
failed/rolled-back handoff, and resumes for verification instead of retrying forever. Uninstall
cancels the request and excludes that worker and every other
update for the full removal transaction before it touches the coordinator or program.
Malformed, cross-turn, or non-update continuation provenance is refused before update work begins;
it is never silently downgraded to an ordinary queued update.

### What the notified channel is told

The notified channel adapter receives these maintenance notices around a successful update. Discord
gives every allowed user a private copy:

- `🛠️ Installing an update — I'm installing the new rundesk update, be back shortly.`
- `👋 I'm back — new rundesk update installed, release notes for v<newer>`, with the release
  notes linked to that version.

The return notice is written only after the new release settles and is consumed only by a gateway
running that exact version. An ordinary stop/start keeps the ordinary gateway notices.

### Settling, which is not the same as arriving

The program-tree swap never replaces `data/`; migration steps may deliberately carry its layout.
When migration work is waiting and `backup_enabled` is on, settlement first makes and verifies the
safety copy described under `backups save`. If that copy cannot be made, migration does not begin
and the update fails with the reason; turning backups on therefore guarantees a rollback boundary
rather than merely requesting one.

**Being on the newest release is not the same as being settled on it.** An update interrupted between
replacing the files and settling — a machine that slept, a terminal that closed — leaves an install
whose code is current and whose configuration and migrations belong to the release before it. So
`rundesk update` settles the install even when it reports `UP TO DATE`; everything it does is
idempotent, and running it again is how you finish an update that stopped halfway.

When `update_enabled` is on, launchd makes one attempt per local calendar day at `update_time`.
The coordinator is outside every gateway process tree and uses the same update transaction as this
command, including ordinary- and team-catalog reconciliation. Before asking for a release it closes
work admission and inspects kernel-held provider and
schedule claims. Active work, or activity that cannot be inspected safely, produces a logged
`DEFERRED` outcome and a private durable request; one detached install-level worker waits until all
turns and schedules finish, then uses the same update transaction without forcing work down. A
request already waiting is preserved and given a worker rather than replaced. Repeated launchd
starts while that worker owns the queue claim are logged and skipped. Failures remain non-zero and
the durable worker retries through the same rerunnable settlement path as a manual update.
The job carries a fixed minimal system `PATH`, so reconciliation and status do not change according
to the shell or development environment that happened to invoke them.

Reconciliation also retires an orphaned automatic update job after its recorded install root has
been absent for at least a day. It removes only a definition whose root fingerprint, filename,
label, program path, working directory, and `RUNDESK_HOME` all agree, and only while the missing
root's parent remains accessible. Working secondary installs, recently absent or unavailable roots,
and malformed or identity-mismatched definitions are preserved. Coordinator changes are serialized
across every install sharing the login directory, including reinstalls and removals. Cleanup claims
the exact stale definition atomically, so a supported older installer that does not use the shared
lock keeps its replacement definition and has its job restored when necessary.

## uninstall

`--confirm` is required. Without it, the command says exactly what it would take and what it would
keep, and removes nothing.

```console
$ rundesk uninstall
uninstall: this would remove rundesk from /Users/you/.rundesk
        take   the command, and /Users/you/.rundesk/app
        keep   /Users/you/.rundesk/data
        keep   /Users/you/.rundesk/backups
        nothing was removed. To go ahead:
        RUNDESK_HOME=/Users/you/.rundesk rundesk uninstall --confirm
```

Confirmation is a flag rather than a typed answer at a prompt, because this has to behave the same
when nobody is watching: a prompt in a script is a command that hangs, and one that assumes "yes"
with no terminal is worse than no prompt at all.

A confirmed purge also requires `--root <dir>` to match the root resolved from `RUNDESK_HOME`.
The environment alone is not accepted as an explicit destructive target because it may already be
ambient or may have been replaced by the provider-turn launcher. A missing or mismatched `--root`
is refused before any removal begins. The preview remains available and prints the exact root-bound
confirmation command, including both values. Every confirmed uninstall prints `uninstall:
confirmed target is <root>` before it starts changing anything.

What it takes, one named thing at a time, never a sweep:

- the root-specific automatic update job and generated shim, before `app/` goes
- **every gateway job this root placed, by the full name launchd knows it by, one agent at a time —
  and before `app/` goes.** A job that outlived the program it points at is a machine trying to
  start a command that is not there, at every login, for ever. And it is one label at a time and
  never a family or a prefix because a job's name belongs to the person rather than to a directory:
  the build this replaces called every install's job the same thing, and one install's uninstall
  booted out another install's live gateway. A job that will not come back stops the removal, rather
  than leaving the machine pointed at a program that is about to be deleted.
- the PATH link — **only where it points into this install's own `app/`**, so a second install on the
  machine keeps its command
- `app/`, whole, unless it looks like somebody's checkout
- `data/`, **only with `--purge`**, including the live credential store below it
- `backups/` — **never.** Not "not by default": there is no argument to this command that reaches
  them. Copies can contain recoverable credentials, so purging the live store is not the same as
  removing every credential from the machine.

A removal that did not happen is reported as a failure. That is the whole point of the command.
