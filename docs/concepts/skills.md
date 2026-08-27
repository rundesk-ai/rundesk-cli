# Every skill is in a catalog

A **catalog** is a repository this install follows. A **skill** is a directory inside one holding a
`SKILL.md`. You install, update and remove catalogs; you grant and revoke skills. Nothing installs a
single skill, because a catalog is what somebody publishes and follows.

The verbs are [`../api/skills.md`](../api/skills.md); writing one is
[`../extending/catalogs.md`](../extending/catalogs.md). Where the files stand is
[`layout.md`](./layout.md).

## Why everything is in a catalog

The build this replaces kept one flat directory shared by every catalog, and it cost exactly what a
flat namespace always costs: a second catalog offering a name the first already had could not be
installed **at all** — not the colliding skill, the whole catalog. An owner who wanted both had to
fork one.

Here a catalog is a directory and nothing is shared, so two catalogs offering `writing-plans` is
ordinary. The collision moves to the one place it is unavoidable — a single agent cannot hold two
directories under one name, because a brain finds a skill by its directory name — and that is what
`--as` answers.

**A skill is addressed `<catalog>/<skill>`, always.** A bare name is refused, naming every catalog
that holds one, because a guess that is unambiguous today stops being so the moment a second catalog
is installed.

## The four kinds of catalog

| Catalog | Comes from | Updated by | Removable |
|---|---|---|---|
| `rundesk` | inside the release | every install and update, out of the release | no |
| `rundesk-skills` | `github.com/rundesk-ai/rundesk-skills` | fetched like any other | no |
| `local` | nowhere — the owner writes into it | never touched by Rundesk | no |
| anything else | the repository it was installed from | `skills update`, and every install and update | yes |

`rundesk` and `rundesk-skills` are dependencies of the product rather than choices made at install
time: an agent is expected to operate the thing running it, and the skills that teach it how are no
more optional than the command is. `local` cannot be removed because removing it would delete work
Rundesk did not write.

**`local` is the one catalog that is flat on disk.** `app/` exists so a fetched tree can be replaced
in one rename with `catalog.json` standing beside it. `local` is fetched from nowhere and never
swapped, so that level would be ceremony in the only catalog a person writes into by hand.

`local` and `rundesk` are **reserved names** and refused at install. `rundesk-skills` deliberately is
not: it is installed by fetching it, which is the ordinary path, and reserving it would mean the
ordinary path had to go round its own rule.

## A grant is the thing standing there, not a record of one

There is no table of who holds what. A grant **is** the entry in the agent's own `home/skills/`
directory, so it is legible, diffable and revocable by hand, and there is no second register to fall
out of step with the first.

```text
data/agents/alan/home/
  skills/
    writing-plans -> ../../../../skills/rundesk-skills/app/skills/writing-plans
    acme-plans/                              a copy, granted --as
  .claude/skills/writing-plans -> ../../skills/writing-plans
  .codex/skills/writing-plans  -> ../../skills/writing-plans
  .agents/skills/writing-plans -> ../../skills/writing-plans
  .grok/skills/writing-plans   -> ../../skills/writing-plans
```

**Presented, never injected.** Nothing puts a skill's text into a prompt. Each brain already walks
the directory a turn stands in looking for skills, so Rundesk links each granted skill into the roots
those brains read and native discovery does the rest.

**One link per skill, never a link to `skills/` itself.** Linking the directory would make a path a
vendor owns an alias for Rundesk's own, so that vendor's skill-installer would write into the source
of truth and anything aimed at that directory would destroy it.

**All four roots, whatever the agent's provider is** — so changing an agent's provider does not
change what it can find.

`managing-rundesk` is a floor: `revoke` refuses it, and `rundesk update` gives it back to an agent
standing without one.

## What a skill declares that it needs

A skill may stand a `rundesk.json` beside its `SKILL.md`, with exactly one key:

```json
{ "needs": { "JIRA_API_TOKEN": "an API token from id.atlassian.com" } }
```

A map of environment variable to **why it is needed**. That one field drives the install preview, the
guided `configure`, which profiles exist, every listing and every `doctor` verdict. A skill with no
`rundesk.json` declares nothing and is never reported as blocked.

**A profile is a whole named set of those values, not a suffix on one.** Three Jira sites is the case
that decides it: a site is a URL, an address and a token that only mean anything together. Profiles
are **found**, not declared — the set of them is whatever suffixes stand on the names a skill
declares, so a fourth account needs no edit anywhere. **A named profile never falls back to a plain
value**, because falling back is how one site's URL comes to be paired with another site's token.

## How an update decides there is something to do

**The far end is authoritative and the version decides nothing.** A catalog whose author edited a
skill without bumping a number is still one this install should be running, so comparing versions
would leave such an install permanently behind while reporting itself up to date.

So the `ETag` from the last fetch goes out as `If-None-Match`, and a catalog nobody has touched
answers `304` with no body. When something has changed the **whole tree is replaced**, which also
repairs a skill somebody edited in place: the repository is the source of truth, and a local edit
inside a fetched catalog is drift rather than work.

**Nothing installed is touched until the new one is known to be good.** Every fetch lands in a
temporary directory and is validated there; a tree that is not a catalog, holds no skills, or holds a
skill no brain would load is refused before anything under `data/skills/` is opened for writing. Only
then is the swap staged and renamed, and put back whole if any part fails.

**One unreachable catalog is not a failed update.** Each is checked inside its own guard, so an
install with four catalogs where the third repository has been deleted is three catalogs that are
fine and one named failure.

## What `doctor` can and cannot see

`rundesk skills doctor` reads nothing and runs nothing: whether a credential is set is asked of the
store, and whether a script can run is decided from what is on the disk. It never reads a credential
*value*. It exits non-zero when anything is wrong and `0` when there is nothing to check at all — an
install with no skills is not an install with a broken one.

The verdicts, and why `PARTIAL` and `UNSEEN` exist, are in
[`../api/skills.md`](../api/skills.md#skills-doctor).
