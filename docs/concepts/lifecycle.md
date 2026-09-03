# This program copy on a machine

Lifecycle owns one question: which copy of Rundesk is on this machine, and how does it move forward
without taking the agents with it. It never owns agent data — that stays under `data/`, and an update
must leave it exactly where it was.

The verbs are [`../api/install.md`](../api/install.md) and
[`../api/configure.md`](../api/configure.md#backups). Where each path is, is
[`layout.md`](./layout.md).

## Three answers, and none of them collapses into another

`rundesk version` asks GitHub what has been published, and refuses to give two answers where there
are three:

| Answer | Means |
|---|---|
| `UP TO DATE` | this is the newest published release |
| `OUT OF DATE` | a newer one exists |
| `UNKNOWN` | nobody could be asked |

**`UNKNOWN` is not a quiet form of `UP TO DATE`.** An install that reported up to date because GitHub
timed out is one that has silently stopped updating itself, and nobody finds out until something else
breaks. It goes to stderr, and the command still exits `0` because the question actually asked —
what version is this — was answered from the machine itself.

The repository an install updates from is deliberately not overridable: an install pointed at one
repository but updating from another drifts, and nothing about it looks wrong.

## Replacing the program is staged, then renamed

Every entry of the new release is copied in beside the old one under an `.incoming` name, and only
when all of them are there does anything move. What was there is renamed aside rather than deleted,
and put back if any part of the swap fails — so a release that half-landed leaves the install on the
version it was, **not on neither**.

**Removing only ever takes what an install placed.** The PATH link is removed only when it points
into this install's own `app/`, and `app/` is removed only when it does not look like somebody's
checkout. An uninstall that deleted a link belonging to another program, or a source tree somebody
was working in, has done something it cannot undo.

**`app/.venv` is built at its destination, never carried there.** Adapters are separate programs and
may need packages; `src/rundesk` itself imports nothing outside the standard library. The environment
lives inside the tree an update replaces, so packages belong to the release that asked for them and a
new tree gets a new environment built from its own requirements.

## Two levels of migration, with different units of failure

|  | install | agent |
|---|---|---|
| what moves | a directory, a configuration value, something a release needs laid down | what one agent keeps, inside its own records |
| where it is | `src/rundesk/lifecycle/steps/` | `src/rundesk/agents/steps/` |
| what has run | one `migration` id in `data/config.json` | one row per step in that agent's `migrations` table |
| unit of failure | the install carries once | one agent that cannot be moved must not stop the others |
| stamping | written immediately after the step | written in the **same transaction** as the step's work |

A step is a file named `NNNN_what_it_does.py` and is **found rather than listed** — there is no table
of steps to forget to update. **A step that has shipped is never renumbered, renamed or edited.**

**A row per step rather than one id, for agents.** An install is one thing and carries once. Agents
are many and are carried at different moments — one made last week, one this morning, one restored
from a copy taken before either — so rows also make *"carried further than this release ships"* a
question with an answer. A key this Rundesk does not ship means a **newer** Rundesk moved that agent
forward, and running an older release's steps over a newer layout is how data is damaged. That is
refused rather than guessed at.

**An agent step is stamped inside its own transaction**, so "it ran but was not recorded" cannot
exist. The install level cannot promise that — its steps move files and its mark is a separate JSON
file — so it stamps immediately afterwards and accepts the window.

**A failed agent step is rolled back per agent**, from a copy of the agent's directory taken first.
Logs, schedules, channels, providers and conversations are excluded from that copy: a step is handed
a connection *and* a directory so it can change tables and files together, and a rollback reaching
only `state.db` would leave files standing beside records that no longer mention them.

## Backups, and the fear they are written around

A copy is the whole of `data/` under a name that says when it was made. **A copy is the thing
somebody reaches for on the worst day they have had with this product**, so anything that leaves one
damaged, half-written or quietly absent has failed at the only moment it existed for.

- **A copy that did not finish is never named like one that did.** The snapshot is staged privately
  on the configured backup filesystem, keeping that location as the save's capacity boundary. Its
  ZIP is written forward without seeking under an `.incoming` name, verified there, and renamed only
  once all of it has landed. A half-copy named like a finished one is worse than no copy — it is the
  one that gets restored.
- **A destination that cannot safely finalize a copy is refused before construction.** A small
  private probe proves write, reread, and rename first and points the owner to `backups set-location`
  when any of them fails. Existing copies are untouched.
- **Retention removes nothing unless its validation pass finishes cleanly.** A failure to clean up a
  private extraction is reported as an operational failure, not as proof that the verified archive
  is unrestorable; the new copy remains and the command says that nothing was let go.
- **Putting one back keeps what it replaces**, so a restore from the wrong name is recoverable.
- **A copy an update takes before carrying is pruned like any other, and only afterwards.** Retention
  runs once the settle has succeeded, so the rollback copy stands for as long as anything could need
  it and an install that keeps seven never holds fifty. A failed settle prunes nothing.
- **A copy that cannot be reached for a moment is not a copy that failed.** Only the shape of the
  bytes makes an archive unrestorable; a read error ends the retention pass with nothing removed.
- New copies are compressed archives; v0.40 directory copies remain valid restore inputs.
- **A backup excludes provider-owned credential homes**, and carries the sealed value store and its
  key. Protect its location as credential-bearing data.

When migration work is waiting and `backup_enabled` is on, settlement makes and verifies a copy
before carrying anything.

## Arriving is not settling

**Being on the newest release is not the same as being settled on it.** An update interrupted between
replacing the files and carrying the migrations leaves an install that reports the new version and
has not finished becoming it. `rundesk status` shows `migration` for exactly that reason, and the
next run finishes the work rather than assuming it was done.

If a provider turn or schedule is active, a manual update is recorded durably and returns instead of
taking work away mid-flight; a detached worker retries it. Restores and updates stand online gateways
down and start exactly those again — members and agents that were already offline stay offline.

## When an update is not doing what you expected

| What you see | Usually |
|---|---|
| `version` says `UNKNOWN` | GitHub could not be reached; this is never reported as up to date |
| `update` says it is up to date and a release exists | the check reached a cached or rate-limited answer — ask again |
| the version moved and something still behaves as before | it arrived and has not settled; `rundesk status` shows `migration` |
| an update returns without doing anything | work was active, so it was queued; the detached worker retries it |
| a catalog failed but the application updated | the three surfaces are reported separately, and a catalog failure never changes the application's exit code |
