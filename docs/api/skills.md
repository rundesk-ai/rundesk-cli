# Skills

## skills

The skills this install has, which agent holds which, and what each of them needs to work. A
**catalog** is what you install, update and remove; a **skill** is what you grant. Nothing installs
one skill and nothing removes one, because a catalog is what somebody publishes and follows.

```console
$ rundesk skills
skills in /Users/you/.rundesk/data/skills
CATALOG         SKILL             AGENTS
rundesk         managing-rundesk  alan, ben
rundesk         writing-skills    —
rundesk-skills  writing-plans     alan
local           my-thing          —

$ rundesk skills grant alan rundesk-skills/writing-plans
alan holds writing-plans
        from     rundesk-skills/writing-plans
        stands   /Users/you/.rundesk/data/agents/alan/home/skills/writing-plans
```

**A skill is addressed `<catalog>/<skill>`, always.** Two catalogs may both hold `writing-plans`, so a
verb that took the bare name would have to guess — and a guess that is unambiguous today stops being
so the moment a second catalog is installed. A bare name is refused, naming every catalog that holds
one, so being wrong costs a copy-paste.

`install`, `update`, `remove` and `forget` say what they would do, do none of it, and **exit non-zero**
without `--confirm`. `grant` and `revoke` do not ask: each is one link in one directory, and somebody
who typed the wrong one types the other verb.

### Two catalogs cannot be removed

`rundesk` ships inside the release and is replaced out of it on every update — it is how an agent
operates *this* version, so it is never fetched and never removable. One skill in it,
`managing-rundesk`, is a floor every agent holds: `revoke` refuses it, and `rundesk update` gives it
back to an agent standing without one. `rundesk-skills` is the general
catalog rundesk depends on, fetched like any other and equally undeletable. `local` is yours and
rundesk never touches it. [`layout.md`](../concepts/layout.md) says why the first two are separate.

Ordinary catalogs are also checked on **every** `rundesk install` and `rundesk update`. An update
additionally checks every installed team catalog and reconciles its members, including when no newer
application release exists — each repository moves on its own schedule. Those catalog checks happen
after the application has settled and **cannot change the compatibility exit code**: an unavailable
repository is a true surface-specific failure to report, and a false reason to report that an
application update failed. The ordinary- and team-catalog surfaces are attempted independently.

### More than one account of the same thing

A skill that talks to something outside this machine says what it needs, and a **profile** is a whole
named set of those values — not a suffix on one. Three Jira sites is the case that decides it: a site
is a URL, an address and a token that only mean anything together.

```console
$ rundesk skills configure rundesk-skills/jira --profile acme
jira needs 3 values for acme
        JIRA_BASE_URL__ACME   your Jira site, e.g. https://acme.atlassian.net
        > 
        ...
profile acme is complete

$ rundesk skills profiles rundesk-skills/jira
profiles for rundesk-skills/jira
PROFILE    STANDING    MISSING
(default)  not set     JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
acme       complete    —
gamma      INCOMPLETE  JIRA_API_TOKEN__GAMMA
```

Profiles are **found**, not declared: the set of them is whatever suffixes are standing on the names a
skill declares, so a fourth account needs no edit to the skill, its catalog, or anything on this
machine. **Every profile is reachable by any agent holding the skill** — nothing binds one to another.

**A named profile never falls back to a plain value.** That is the rule the shape exists for: falling
back is how one site's URL comes to be paired with another site's token, and the request succeeds
against the wrong company. A profile carries all of its own values or it is reported incomplete.

Values are typed, never passed as arguments, and never printed back — `env` says why. `configure` exits
non-zero when the account is still incomplete, and `forget` empties a whole account at once.

### doctor

`rundesk skills doctor` says what cannot be used and why, names the one command that fixes it, and
**exits non-zero when anything is wrong** — the way `env check` does, so a script can gate on it. It
reads nothing and runs nothing: whether a credential is set is asked of the store, and whether a
script can run is decided from what is on the disk.

```console
$ rundesk skills doctor
alan
  jira           rundesk-skills  PARTIAL   2 of 3 profiles are usable
      acme  ready
      beta  ready
      gamma  INCOMPLETE
          JIRA_API_TOKEN__GAMMA — an API token from id.atlassian.com
  writing-plans  rundesk-skills  READY     needs nothing
  old-thing      —               DANGLING  the grant points at nothing
skills: 2 of 3 cannot be used:
        rundesk skills configure rundesk-skills/jira --profile gamma
        rundesk skills revoke alan old-thing
```

The columns are measured against what is actually there rather than fixed, so a long catalog name
does not run into the next one. The findings go to stdout and the summary to stderr, so a script can
read one and ignore the other — and the findings are flushed first, or the summary would appear above
what it summarises when both are merged into one pipe.

| Verdict | Means |
|---|---|
| `READY` | every profile is complete, and every command it ships would run |
| `PARTIAL` | at least one profile is usable and at least one is not |
| `BLOCKED` | no profile is usable — a required value is missing everywhere |
| `UNRUNNABLE` | every credential is in place and a command it ships is not executable |
| `UNSEEN` | the grant is there and no provider can find it; `rundesk update` links it, unless something of yours holds the name |
| `STALE` | a copied grant is behind the catalog it came from; `rundesk update` remakes it |
| `DANGLING` | the grant no longer resolves — its skill left its catalog, or the catalog went |
| `BROKEN` | the skill itself will not load, or what it declares cannot be read |

`PARTIAL` exists because two working Jira sites and one half-configured is neither a healthy
integration nor a broken one, and collapsing it either way would cry wolf on a working setup or hide
the site that fails at three in the morning.

`UNSEEN` exists because a grant and its linking are two separate writes. The link into each provider's
own root is made after the grant, under a lock of its own, so it can be refused on its own — and what
that leaves is a skill that is correct in every listing and invisible to every brain. `grant` sends anybody who
meets that refusal here, so this is the command that has to be able to answer it. (`revoke` does not,
and deliberately: it takes the grant away before it links, so by the time it can fail there is no
grant left for this command to look at. It names `rundesk update`, which clears the leftover links.)

**`UNSEEN` has two causes and only one of them is rundesk's to fix.** A provider root with nothing
under the name is linked by the next sweep, so `rundesk update` repairs it. A root where a link or
directory of *your own* stands under that name is one rundesk will never replace — so it says what is
in the way and offers no command, because there is not one: move that entry, or hold the skill under
another name with `rundesk skills grant … --as <name>`.

Writing a skill or publishing a catalog is [`catalogs.md`](../extending/catalogs.md).
