# Teams

## teams

A team catalog adds version-controlled named agents to an ordinary skill catalog. Preview and
confirmation are separate:

```console
$ rundesk teams install ./development-team --provider codex
install: this would install team development-team from ./development-team
        catalog  rundesk-skills — reuse installed from https://github.com/rundesk-ai/rundesk-skills; require writing-plans
        member   forge — create with provider codex
                 replace AGENTS.md and CLAUDE.md; remove MEMORY.md; allow only development-team/implementing, rundesk-skills/writing-plans plus Rundesk-required skills; weekly upkeep on; leave gateway stopped
        nothing was installed or changed. To go ahead:
        rundesk teams install ./development-team --provider codex --confirm
```

`--provider` is used for the new agents created by installation. Installation refuses any declared
member name that already exists and prints the exact `rundesk agents remove <agent> --confirm`
command required before retrying. This clean-start boundary ensures every member begins with the
catalog-owned instructions, memory policy, delegation scope, skill allowlist, and weekly upkeep
setting.

A confirmed installation that fails part-way through leaves no team. A catalog it installed is taken
away again and every agent it created is removed, so a name that was free before the attempt is free
after it; a catalog that was already installed as a skills-only catalog and was promoted to a team
goes back to being that catalog, at the version and tree it had, with the grants anyone held from it
intact. A dependency catalog installed to reach that point deliberately stays installed, granted to
nobody, and the failure names it — installing it again is wasted work, and removing a catalog
other teams may share is not this command's to do. A restore that cannot itself finish says what it
could not put back instead of reporting either outcome.

Schema 2 teams may declare shared skill catalogs by exact name and source. The preview says whether
each one will be installed or reused. A missing catalog is fetched and validated before confirmation
changes anything; an installed catalog is reused without reinstalling only when its recorded source
matches and every referenced skill exists. Member skill allowlists use fully qualified
`<catalog>/<skill>` addresses. Existing schema 1 teams remain self-contained and compatible.
Removing a dependency, or updating it past a referenced skill, is refused until the installed team
declaration no longer requires it.

`rundesk teams update <team>` remains the explicit preview-and-confirm command for one team. It
fetches the recorded source and performs the same reconciliation, repairing local instruction,
memory, delegation, and skill-allowlist drift even when the fetched tree is unchanged.
`--source <repository>` replaces the recorded GitHub repository or local directory in that same
guarded update. A source change never reuses the old source's ETag, validates that the new catalog
has the installed team's exact name, and is named in both the preview and completed result. The new
source is recorded even when its tree is byte-identical. A reconciliation failure restores the old
catalog tree, recorded source, and member state together. A newly
declared member name already held by an agent no team manages is refused, by the preview as well as
the confirmation, and that agent keeps its files, records, and grants; remove it first with the
`rundesk agents remove <agent> --confirm` the refusal names. A member whose records cannot be read
is refused before anything moves, as is anything that is neither a file nor a symlink standing
where a managed instruction or memory page belongs.

A reconciliation that fails part-way through puts the catalog version back, with every member's
pages, records, upkeep, and delegation scope, and the grants of every agent that catalog reaches;
an agent it reaches only through a grant keeps its own pages and records. It takes away a member it
had just created, and removes nothing that was already there; a restore that cannot itself finish
says what it could not put back rather than reporting the update as done. The explicit install and
update commands leave every member gateway stopped. Start only the agents you want to use with
`rundesk gateways start <agent>`.

Manual `rundesk update` and the daily updater check every installed team without a separate
confirmation step. They fetch and validate the declaration and every catalog it declares as a
dependency before a gateway moves or any catalog, team, or member is written, installing a missing
dependency and reusing a matching installed one. They keep catalog swap and member reconciliation
behind work admission, and restore exactly the member gateways they stood down; members already
offline stay offline. They refuse an unmanaged name, an unreadable member's records, and a page
nothing could put back — each before a member gateway moves — and put back what a part-way
failure had already changed, on the same terms as the explicit command. A
team that cannot be fetched, validated, or reconciled does not stop the other catalog surfaces, and
its outcome is named. Fetch
or validation failure leaves its last working catalog untouched; turn admission refuses any member
whose managed state cannot be repaired completely.

Before any later provider turn is admitted, Rundesk performs the same reconciliation for that one
member from the installed catalog. This is a local drift repair and performs no fetch; a new catalog
version arrives through the explicit confirmed team command or the manual/daily update lifecycle.

The member's `skills` array is a positive allowed list, not a deny list, and may be empty.
Reconciliation removes any unlisted grant, regardless of catalog, while preserving Rundesk's
required operating skill and its
conditional delegation skill. Editing the positive list is how a team version adds or removes a
stack-specific or task-specific capability. The member's required `self_improve` boolean enables or
disables Rundesk's protected weekly upkeep and is repaired from the catalog on later turns. A member
removed from a later team version is no longer managed and is not deleted. Team catalogs execute no
installation hook.
Installing the same repository with `skills install` intentionally installs only its skill
catalog: it creates no agents and writes no team marker. That installation updates and removes like
any ordinary skill catalog. Installing the team later promotes that catalog in place and creates
the declared agents; the already installed skills remain available.

Once a catalog was installed through `teams install`, ordinary `skills update`, ordinary catalog
refresh, and `skills remove` cannot move it independently of its agents. Only the team command or
the combined manual/daily update lifecycle moves it together with member reconciliation.
An agent turn may run confirmed skill- and team-catalog operations when the owner authorized that
effect and the turn's configured tool access can invoke Rundesk. Rundesk does not infer owner
authorization from the environment. The same preview, `--confirm`, validation, collision, locking,
reconciliation, and stopped-gateway guards apply whether the command came from a terminal or a turn.
