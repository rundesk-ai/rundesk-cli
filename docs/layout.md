# Where an install keeps everything

**One root, and every other place derived downward from it.**

`RUNDESK_HOME` is the only location rundesk reads. It defaults to `~/.rundesk`, and everything else
is a function of it:

```
$RUNDESK_HOME/
  app/            the program itself
  data/           everything you accumulate — agents, logs, skills, configuration, secrets
    automatic-update.json  the last completed local-day automatic attempt and outcome
    automatic-update-job.json  receipt for the definition successfully loaded by launchd
    queued-update.json  a durable manual update request waiting for active work to finish
    logs/automatic-updates/ dated outcome logs and bounded launchd captures
    secrets/      sealed values and the key that opens them
  backups/        compressed ZIP copies of data/ (and restorable v0.40 directory copies)
  projects/       the shared directory work is checked out into
  .rundesk.lock   held while one command at a time changes this install
  .rundesk-gateways.lock  held while an update and gateway starts take turns
  .rundesk-update.lock  held by one manual or automatic update
  .rundesk-update-queue.lock  held by the queued worker, or by uninstall while excluding it
  .rundesk-work-admission.lock  closes the automatic-update/new-work race
  rundesk-automatic-update  stable program launchd invokes across app swaps
```

| Below the root | What may reach it |
|---|---|
| `app/` | an update replaces it whole; an uninstall takes it whole |
| `data/` | never touched by an update; kept by an uninstall unless a purge asks for it |
| `backups/` | survives removal, including a purge; may be a link to another disk |
| `projects/` | yours, never rundesk's to tidy |
| `.rundesk.lock` | rundesk's own; taken away by an uninstall |
| `.rundesk-gateways.lock` | rundesk's transient gateway/update barrier; taken away by an uninstall |
| `.rundesk-update.lock` | serialises manual and automatic updates; taken away by an uninstall |
| `.rundesk-update-queue.lock` | ensures one detached queued-update worker and excludes it throughout uninstall; transient and safe to leave empty |
| `.rundesk-work-admission.lock` | briefly held while work starts and throughout an automatic update's busy decision |
| `rundesk-automatic-update` | generated coordinator shim; survives updates and is taken by uninstall |

`.rundesk.lock` is the file one command at a time holds while it changes the install. It stands
beside the directories rather than inside `data/` on purpose: the operations it makes safe *move
`data/` itself*, and a lock inside the thing being renamed away is a lock two commands can end up
holding different copies of. That is not hypothetical — a `configure` landing in the moment a
restore had renamed `data/` aside recreated the directory, reported success, and had its change
deleted by the restore's own rollback.

One data lock for the whole install rather than one per directory, because the races worth stopping are
between *different* commands touching different things, and a lock per directory lets exactly those
through.

`.rundesk-gateways.lock` answers a different process-lifecycle boundary. An update holds it from
gateway preflight through the new release settling; a gateway takes it before claiming an agent. A
gateway that had to wait refreshes its interpreter first, because the modules it imported may have
been replaced while it waited. It cannot reuse `.rundesk.lock`: the updater's child legitimately
takes that data lock while settling, and a parent holding it across the handoff would deadlock.

The automatic coordinator is a separate root-fingerprinted launchd calendar job,
`ai.rundesk.<fingerprint>.update`, whose plist stands in `~/Library/LaunchAgents`. It is not a child
of a gateway, so standing every gateway down does not stop the daily schedule. Its plist carries the
one `RUNDESK_HOME` it belongs to; no label or state is shared between installs. launchd interprets
the configured hour and minute in local time. A completed local calendar day is recorded so a
repeated firing, including a repeated wall-clock hour, does not perform a second attempt.

**Nothing sweeps it, and a stale file is not a held lock.** The lock is the `flock`, not the file:
the kernel drops it when the process ends, however it ended — cleanly, on a crash, on `SIGKILL`, on
the power going. Demonstrated rather than assumed: a process holding it was `SIGKILL`ed and the next
command had the lock immediately. A sweep would be actively worse, because removing the file while
another process holds a lock on it means the next caller creates a *new* file and locks that, and
both then believe they have it — which is the failure lockfile-by-existence schemes have and this
one does not.

What *is* worth being careful about is how long a command waits for it. A whole-directory copy
legitimately holds it for a long time: a 120MB `data/` of sixty thousand files measured 9.2 seconds,
and a real install with a database per agent is larger. So the wait is the caller's to choose — a
few seconds for one small file, minutes for something that moves a directory — and a command that
gives up says another may still be running rather than claiming something has gone wrong.

Set the root and every one of those moves with it:

```sh
RUNDESK_HOME=/tmp/somewhere rundesk status
```

## An agent is a directory, and everything it has is inside it

Agents stand under `data/agents/`, one directory each, named as that agent is:

```
data/agents/<name>/
  state.db          what makes this directory an agent — everything it remembers
  home/             where the agent starts, with compact rules, memory, and durable work areas
  logs/             what its gateway said: a file per day, and what launchd caught
  schedules/        what each firing holds, wrote, and was: <schedule>.lock, .out and .json
  channels/<kind>/  one adapter's records, logs, staging, and dated inbound files
  gateway.lock      held by the one gateway running this agent, for as long as it runs
  gateway.json      what that gateway wrote down about itself
  gateway-update.json  transient one-shot update notice, omitted from backups and consumed on use
  rundesk-gateway-<name>   the program launchd starts, written when the job is placed
```

**`state.db` is what makes the directory an agent, and nothing else is.** Not the directory
existing — a half-made one exists — and not `home/` or `logs/`, which somebody could have made by
hand. So a stray directory is not listed as an agent and cannot be operated on as one, and an
interrupted `agents add` leaves litter rather than something wearing an agent's name and not being
one.

The configuration row in `state.db` also keeps this agent's outbound delegation scope as a nullable
JSON array. `NULL` means the default, any other available agent; `[]` means none, making this agent
inbound-only for named-agent work; and a non-empty array is the exact allowlist. The setting changes
only where this agent may delegate. It never prevents another agent from delegating work here.
Existing agents carried into the release receive `NULL`, so adding the setting does not silently
narrow a team that already delegates. Removing an agent prunes its name from every explicit array
before removal, so recreating that name does not inherit prior allowlist authority; `NULL` remains
unrestricted and inbound delegation remains unchanged.

Each delegation row may also hold one admission-resolved provider and an optional explicitly
supplied model for that bounded task. Both are nullable: `NULL` in both means no scoped override and
preserves late binding to the target agent's configuration when work is claimed. A provider path is
stored canonically so another working directory cannot reinterpret it. Recorded values are
immutable across answer, failure, stop, resume, gateway replacement and process loss; none is copied
into the target agent's configuration row.

The same row keeps an explicit operating `role`: `domain` or `specialist`. Existing agents migrate
to `domain`, which is also creation's default. Role describes the agent's work lifecycle only; it
does not grant skills, change provider or delegation scope, create a Desk, or confer authority.
Rundesk uses it to group team listings and choose the initial standing-rule template.

An opted-in update or safe self-gateway restart keeps its transient continuation ledger in that
same `state.db`. A row names the origin by local turn/message ids and keeps lifecycle/continuation
states, bounded product outcomes, and observed version/pid. It never copies an owner prompt,
provider session handle, channel/person identity, credential, agent name, or filesystem path.
Transactional state changes make a duplicate or crash claim at-most-once; completed, suppressed,
and stranded `resuming` rows remain auditable and are never replayed. Ordinary update/restart paths
create no row. A backup keeps the ledger for audit but suppresses actionable rows in its staged
snapshot without changing the live database. Restore repeats that suppression before gateways may
return—including for a database preserved through the byte-copy fallback—so older state cannot
replay transient work.

**Rundesk never sweeps an agent's `home/`.** New domain and specialist agents start from separate
canonical rule templates, with identical bytes in `AGENTS.md` and `CLAUDE.md`. After creation those
files belong to the agent and owner: changing `role` does not rewrite either one. The agent keeps
compact cross-run continuity in
`MEMORY.md`, including small pointers to active external projects; changing project detail stays in
its project or an earned shared index. Ordinary work removes only temporary files and directories it
created. A focused maintenance task may compact linked indexes and remove confirmed obsolete
agent-created clutter, but an old-looking or unfamiliar
file is somebody's data, not permission to tidy it away. A purpose-named index such as `PROJECTS.md`
is ordinary home content: Rundesk does not create, read, or sweep it.

Every agent starts with five purpose-named areas and a compact README in each:

```text
home/
  plans/       durable resumable plans that do not belong in a project
  research/    reusable, sourced findings owned by the agent
  scripts/     tested agent-owned automation for repeated work
  retros/      dated evidence-based self-improvement entries
  tasks/       active briefs for resumable multi-turn or delegated work
```

The notes are filled in only when absent and never replace an owner-edited answer. The directories
organize agent-owned work; they are not a reason to move project state home or keep task scratch.
`tasks/` holds only active resumable briefs, linked to a canonical source when one exists and removed
when their outcomes close. A focused upkeep may keep `retros/YYYY-MM-DD.md`; the initiator supplies
the evidence interval and entry date, and a rerun updates that one entry. The bundled maintenance
reference bounds each entry but keeps the history. Rundesk never sweeps these areas, and an older or
unfamiliar file is never treated as disposable.

**The names inside are fixed and they are the same for every agent**, which is the whole reason they
are inside. The build this replaces put them beside the name instead — `<name>.lock`, `<name>.log`,
`<name>.json`, all flat in one directory — so an agent called `foo.log` and an agent called `foo`
wanted one file between them, and one agent's log was the other agent's whole existence. It grew a
published list of every suffix a gateway might ever write, and a name checker that read the list
back, to make a flat namespace safe. This layout deletes that class of problem rather than defending
against it: `gateway.lock` inside `foo/` and `gateway.lock` inside `foo.log/` are two different
files, and no list anywhere has to say so.

`schedules/` is where a firing keeps the three things it needs and the agent's records cannot hold.
`<schedule>.lock` is claimed before the work starts and **held by the work itself**, so it lives
exactly as long as that work and is dropped by the kernel however it ends — which is what makes "is
this still running" a question with an honest answer after a crash, and what stops a terminal and a
gateway each starting a copy. `<schedule>.json` says which minute the firing was for and what its
process id is, written before the spawn so that a gateway killed outright still leaves something
pointing at the work. `<schedule>.out` is everything that schedule's work has ever written, appended
across runs and rotated by size.

One protected schedule name, `weekly-self-improve-upkeep`, belongs to Rundesk rather than to an
owner-authored cron. Its inert database row is created when the first seven-date usage cycle is
ready and carries the frozen prompt and last attempt. The per-agent `config.self_improve` boolean,
which defaults on, is the only switch. Distinct terminal-turn dates and the last attempt remain in
that same agent's `state.db`; no install-wide usage or upkeep state exists.

`channels/<kind>/in/YYYY-MM-DD/<message>/` holds files that arrived through a channel. Rundesk owns
those copies and sweeps whole days after 60 days. Outgoing files have no directory here: they are
sent in place from the explicit local path in an answer and remain owned by the project, tool, or
person that created them.

Beside that stand four things belonging to whichever gateway is hosting the channel, none of which
is configuration and none of which a person edits: `lock`, the claim an adapter holds for as long as
it lives; `record.json`, which process it is; `stderr.log`, what it wrote that was not a record; and
`will-not-start.json`, written when an adapter has exited `78` to say that this gateway has stopped
trying to start it. The last is what `channels show` and `channels doctor` read to tell a channel
that was given up on from one whose gateway is simply not running, and it is removed the moment
something starts that channel again.

It is one of the two directories a migration does not copy aside and put back, along with `logs/`:
both grow without bound, and putting a lock file back underneath a child that is still running would
be putting back a claim that has moved on.

An agent's directory is only ever removed by `rundesk agents remove`, one named thing at a time, and
the directory itself goes only if it is then empty — anything you put in there is kept, along with
the directory holding it. Scope configuration, explicit-scope pruning during removal, and direct
delegation admission are serialized by the install state-change lock.

## Every skill is in a catalog, and a catalog is a directory

Skills stand under `data/skills/`, one directory per catalog:

```
data/skills/
  rundesk/                  ships inside the release — how to operate this rundesk
    catalog.json            what rundesk wrote down about where it came from
    app/                    the catalog's own tree, verbatim
      manifest.json         what makes the directory a catalog
      skills/managing-rundesk/SKILL.md
      skills/managing-rundesk/references/maintenance.md
      skills/managing-rundesk/references/retrospective.md
      skills/managing-rundesk/references/self-improvement.md
  rundesk-skills/           fetched from GitHub — the general catalog rundesk depends on
  local/                    yours. Never fetched, never removed by rundesk
    manifest.json
    my-thing/SKILL.md       flat — no app/, because nothing ever swaps this one
```

**`app/manifest.json` is what makes the directory a catalog**, the same way `state.db` makes a
directory an agent. `catalog.json` deliberately is not: it records where a catalog was *fetched* from,
and `local` was never fetched from anywhere.

**Which skills a catalog holds is found rather than listed** — every directory under `app/skills/`
with a `SKILL.md` in it. The build this replaces listed each one in the manifest with its path, so
three places had to agree about one name: the manifest entry, the directory, and the frontmatter
inside. They disagreed, and every disagreement was a catalog that installed and then behaved as
though a skill were not there.

**Nothing shares a name, because nothing shares a directory.** That flat namespace was the other
thing the previous build got wrong here: one `data/skills/<name>` for every catalog meant a second
catalog offering `writing-plans` could not be installed at all — not the colliding skill, the whole
catalog. An owner who wanted both had to fork one. A skill is now addressed `<catalog>/<skill>`, and
the collision survives only where it is unavoidable: a single agent cannot hold two directories under
one name, because a brain finds a skill by its directory name.

### Two of them cannot be removed, for two different reasons

`rundesk` ships **inside the release** and is replaced out of it on every install and update. What is
in it is how to operate *this* rundesk and how to write a skill for it, so it is coupled to the
version — a machine on an older release must not be handed a newer release's instructions, which is
exactly what would happen if a repository on its own schedule governed it. It is never fetched from
anywhere, and it is the reason a machine with no network finishes installing with working skills.

`rundesk-skills` is **fetched**, like anybody else's catalog. Nothing in it is coupled to a version —
how to write a pull request does not change when rundesk does — so it lives on its own release
schedule, where a correction reaches every install without cutting a rundesk release.

`local` is where your own skills go. Nothing fetches into it, and nothing rundesk does removes it.

### A grant is a link in the agent's own directory

Granting a skill copies nothing. A link stands in that agent's `home/skills/`, and rundesk links each
skill from there into every root a provider CLI reads:

```
data/agents/alan/home/
  skills/writing-plans -> ../../../../skills/rundesk/app/skills/writing-plans
  .claude/skills/writing-plans -> ../../skills/writing-plans
  .codex/skills/writing-plans  -> ../../skills/writing-plans
  .agents/skills/writing-plans -> ../../skills/writing-plans
  .grok/skills/writing-plans   -> ../../skills/writing-plans
```

**There is no record of who holds what** — the grant *is* the entry standing there, so it is legible,
diffable and revocable by hand, and there is no second register to fall out of step with the first.
Which catalog a grant came from is read back off the link's own target rather than written down
anywhere.

**One link per skill, never a link to the whole directory.** Linking `skills/` itself would make a
path a vendor owns an alias for rundesk's own, so that vendor's skill installer would write into the
library and anything aimed at that directory would destroy it.

The one exception is `rundesk skills grant --as <name>`, which is how one agent holds two skills of
one name. That grant is a **copy** with its frontmatter rewritten to match the directory it stands in,
because a brain that found the two disagreeing would index it under a name nothing granted. A copy can
go stale, so it carries `.rundesk-grant.json` naming where it came from, and every update makes it
again.

## The one thing that is not below the root

```
~/Library/LaunchAgents/ai.rundesk.<fingerprint>.gateway.<agent>.plist
```

That is a real exception to this page's whole thesis, so here is why it is one rather than a leak.

It is where macOS requires a login job's definition to be. Every job a person has is registered in
one place belonging to *the person*, and there is no directory below `RUNDESK_HOME` that `launchd`
would ever read. So the choice is not between one root and two; it is between a gateway that starts
at login and one that does not.

**What `RUNDESK_HOME` still decides is which file that is.** The name carries a fingerprint of the
resolved root, so a scratch install and a real one write different files and neither can reach the
other's — and nothing in rundesk ever matches a prefix or sweeps that directory. Redirect the root
and the plist moves with it, exactly like everything above; it simply moves to a different name in a
directory that was never ours.

That fingerprint is not decoration. A job's name lives in the person's login session and
`RUNDESK_HOME` cannot isolate it, and the build this replaces gave every install's job the same
name — so a second install's uninstall booted out the live install's gateway.
[`gateways.md`](gateways.md) has the rest of it.

`rundesk gateways stop` takes the plist away with the job, and `rundesk uninstall` takes back every
job this root placed before it removes anything else. Nothing else in this product writes into that
directory.

## The copies may live elsewhere, and that is still one variable

`rundesk backups set-location /Volumes/Big/rundesk-backups` moves the copies to another disk and
leaves `backups/` as a **link** to it.

A link and not a setting, and that is the whole point. `RUNDESK_HOME` stays the only location rundesk
reads, `backups/` is still `$RUNDESK_HOME/backups`, and nothing anywhere gained a second place to
look — the filesystem holds the indirection rather than the configuration. Redirect the root and
everything still moves with it.

Install and update settlement never follows that link merely to refresh Rundesk's explanatory
`README.md`. The external directory belongs to the backup store, may be unavailable to a background
launchd process, and is entered only by a backup operation that actually needs the copies.

`rundesk status` shows both, because they are two different questions:

```
backups  /Users/you/.rundesk/backups → /Volumes/Big/rundesk-backups
```

And when that disk is not plugged in, it says so rather than reading as an install with no copies:

```
backups  /Users/you/.rundesk/backups → /Volumes/Big/rundesk-backups — that directory is not there
```

## Why the values you place are below `data/`

`rundesk env set` keeps a token in `data/secrets/` because credentials are owner state and a backup
must be able to restore a working install. Backups carry the store and restore the credential state
they contain.

The directory is `0700` and every file in it `0600`, repaired on each write, and neither the
directory nor the key may be reached through a symlink — a link decides where bytes land, and can
send the one thing that opens every value outside the tree rundesk owns.

Each value is sealed with a key kept beside it, so nothing is readable text on the disk. Each is
also signed **over its name as well as its bytes**, so a value that was tampered with *or moved to
a different name* is refused rather than opened: signing the bytes alone would let anybody able to
edit the file swap two sealed values between names, with no key at all, and a program asking for
its Discord token would be handed the Slack one and send it to Slack.

**The key sits beside the values because a gateway has to start at boot with nobody typing**, which
is the honest limit of the whole thing: this stops a credential being readable text on a disk or in
whatever a filesystem hands back after a delete. It does not stop somebody with the owner's account,
root, or a complete backup. Protect and encrypt backup media accordingly.

## What a copy does not carry

A copy is made with the standard library, and on macOS that quietly means **extended attributes and
resource forks are not copied** — Finder tags, Finder comments, and anything else stored beside a
file rather than in it. Not a choice: CPython has no `os.listxattr` on macOS at all, so the standard
library's own copy step is a no-op there, on every version including the 3.9 floor.

The contents of every file are copied exactly. It is worth knowing before you rely on a restore to
bring back something that was never in the bytes.

## Why one variable and not twelve

The build this replaces read a dozen independent variables — one each for the install, the data,
backups, agents, run state, logs, launchd jobs, secrets, the skill library and the scripts directory —
each with its own default under the owner's home.

That is one variable too many, and the failure it produces is always the same: somebody redirects
eleven of them, believes they have isolated the run, and the twelfth resolves to the live install.
That is not hypothetical. It deleted an owner's installed skills, wrote a real credential into their
secrets directory, and unregistered the job that kept their machine updating itself — each time while
reporting an ordinary success, and each time with nothing in the output naming the directory it had
actually used.

With one root, a partial redirect is not something you can express.

## Unset and empty are different answers

Nobody having said where the install is means the default, and is ordinary.

A variable that is *there and empty* means something tried to say and produced nothing — a script
whose own variable was unset, a scrubber that ran in the wrong order. Reading that as "nobody said"
points the command at your live install at the exact moment something was trying to point it
elsewhere, so it is refused out loud instead:

```
status: FAILED — RUNDESK_HOME is set and empty, which is not the same as unset
```

## Roots that are refused

Everything below the root is a directory an uninstall may delete, so a root that is too broad is one
command away from taking your home with it. These are refused rather than worked with:

- an empty value, and a value that is only whitespace
- a relative path — it would resolve against whatever directory you happened to be in
- `/`
- your home directory itself

The last one is not theoretical either: the installer this replaces recorded that pointing an install
at a home directory once emptied it, and then printed success.

## Where the program is, is a different question

`rundesk status` reports `program` as well as `home`, and they are not derived from each other.

A checkout install has the program in a source tree while the data belongs under your home, so
deriving the second from the first is right exactly until somebody runs the command from a checkout —
which is what a developer does every time.
