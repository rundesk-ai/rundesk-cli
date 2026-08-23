# Writing a skill, and publishing a catalog

A skill is a directory holding a `SKILL.md`. Every provider CLI rundesk runs already reads that
format, so nothing here is rundesk's invention and a skill you write works outside rundesk too.

A **catalog** is a repository of them. It is the unit rundesk installs, updates and removes; a skill is
the unit it grants to an agent.

## Choosing a catalog boundary

Add a skill to an existing catalog unless a separate repository has an enduring boundary. Create a
catalog only when at least one of these differs materially:

- runtime or operating-system requirements;
- permission, credential or security model;
- accountable owner or maintainer group;
- compatibility contract with a provider, platform or distributed CLI; or
- release lifecycle and support cadence.

Do not create a catalog merely for a topic label or one skill. Skills in one catalog may share
repository tooling and provider infrastructure, but every installed package must work without another
repository checkout. Copy or package required runtime support inside the owning catalog; never create
a cross-repository runtime dependency.

A catalog that owns a tested set of named Rundesk agents is a **team catalog**. Use that boundary
only when the catalog is responsible for keeping those agents' instructions, delegation scope, and
positive skill allowlists in step across installations. Its schema and guarded lifecycle are specified in
[`requirements/team-catalog.md`](requirements/team-catalog.md); ordinary topical skill catalogs do
not need team files.

## Building a catalog repository

Use this root layout for a shared catalog:

```text
catalog-repository/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug-report.md
│   │   ├── change-proposal.md
│   │   └── config.yml             disables blank issues
│   ├── pull_request_template.md
│   └── workflows/                 required validation gate
├── skills/
│   └── skill-name/
│       ├── SKILL.md               required
│       ├── rundesk.json           only when environment values are required
│       ├── scripts/               only for executable behavior
│       ├── references/            only for conditional detail
│       └── assets/                only for reusable output material
├── tests/                         catalog and package contract tests
├── AGENTS.md                      repository operating contract
├── CLAUDE.md                      byte-identical copy of AGENTS.md
├── ENVIRONMENTS.md                only for runtime/configuration catalogs
├── LICENSE                        required repository license
├── README.md                      purpose, install, contents and support boundary
├── RELEASING.md                   compatibility, validation and publication process
├── THIRD_PARTY_NOTICES.md         only when adapted work requires attribution
└── manifest.json                  catalog identity and version
```

A team catalog adds `team.json` and one canonical `agents/<member>/AGENTS.md` per declared member.
It remains data-only: do not publish an install hook or migration script and do not place provider
credentials, channel configuration, projects, or installation-local model choices in it.
Every declared member name must be absent from the target installation; the owner removes a
same-named agent before installing the team so catalog members always start from canonical state.
Each member also declares whether Rundesk's protected weekly upkeep is enabled.

### Building a team catalog

Start with the catalog layout above, then add `team.json` and one instruction file for each member.
This is a complete two-member declaration:

```json
{
  "schema": 1,
  "name": "acme-development",
  "members": [
    {
      "name": "forge",
      "description": "Implements approved product changes and returns verification evidence.",
      "instructions": "agents/forge/AGENTS.md",
      "skills": ["implementing-code", "testing-code"],
      "delegates_to": ["vera"],
      "self_improve": true
    },
    {
      "name": "vera",
      "description": "Reviews changes for correctness, safety, and maintainability.",
      "instructions": "agents/vera/AGENTS.md",
      "skills": ["reviewing-code"],
      "delegates_to": [],
      "self_improve": true
    }
  ]
}
```

The `name` must match `manifest.json`. Every skill name must exist under `skills/`, every
`instructions` path must stay inside `agents/`, and each member needs a unique Rundesk-safe name.
Keep provider accounts, models, credentials, channels, schedules, and projects out of the catalog;
those choices belong to each installation.

Test the catalog from its local checkout before publishing it:

```sh
rundesk teams install ./acme-development --provider codex
rundesk teams install ./acme-development --provider codex --confirm
```

The first command is a dry-run preview. Use a disposable Rundesk installation for the confirmed
acceptance test so it cannot replace or collide with live agents. After publishing the repository,
users install it with the same commands and its GitHub URL. Team members are created with their
gateways stopped; the owner starts only the agents they want.

The full validation, reconciliation, ownership, and safety contract is in
[`requirements/team-catalog.md`](requirements/team-catalog.md).

Do not add an empty optional skill directory. `ENVIRONMENTS.md` belongs only in a catalog whose
skills ship runtime code, select accounts or require configuration across environments; omit it from
guidance-only catalogs. Keep repository instructions in the root guides, consumer setup in the
README, environment selection in `ENVIRONMENTS.md`, and release mechanics in `RELEASING.md`.
Every public catalog carries a `LICENSE`. When a skill adapts or distributes upstream work, preserve
the upstream license and required notices in the package and add `THIRD_PARTY_NOTICES.md` at the
repository root when repository-level attribution is required. Never remove or weaken an upstream
license, copyright notice or attribution condition while adapting the work.

### Agent instructions

Make `AGENTS.md` an executable contract for working in the repository, not a project description.
Keep `CLAUDE.md` as a regular byte-identical copy. Use exactly this top-level order and no additional
`#` or `##` headings:

```text
# AGENTS
## Purpose
## Before you work
## Repository layout
## Package and artifact contract
## Safety and approval gates
## Delegation
## Architecture and conventions
## Documentation duties
## Build, test, and run
## Pull requests and releases
## Definition of done
```

Under those headings, state the actual tech stack, sources of truth, architecture direction, public
compatibility boundaries, approval gates, privacy rules, exact full test gate, release contract and
observable definition of done. Preserve stronger repository-specific invariants. Add a gate test that
compares the two guide files byte for byte and extracts the ordered top-level headings.

### README and repository tests

The README is the consumer contract. An intro and badges may precede these headings; a standalone
catalog then uses exactly this order:

```text
## Skills
## Install
## Requirements
## Repository layout
## Development
## Creating a skill catalog
## Contributing
## Releases
## License
```

It identifies the catalog, explains the shortest preview and confirmed install path, lists every
discovered skill with its purpose, states shared requirements and authentication boundaries, links
environment guidance only when it exists, and directs contributors to the issue, pull-request and
release contracts. A product repository that also bundles skills may preserve its product-oriented
README navigation, but it links this guide and Rundesk's supported first-party catalog directory.

Use one test runner locally and in CI. It must discover and fail on missing work, validate the
manifest and every package, compare directory/frontmatter names, bound descriptions, parse
`rundesk.json`, check script executability, and keep the README and discovered packages in agreement.
It also asserts root-guide byte parity and heading order, the pull-request template's eight headings,
and the shared issue-template frontmatter and headings. Add focused offline tests for every script and
public workflow. Run the repository's exact lint, format, parse and shell checks and inspect counts.

Use `.github/ISSUE_TEMPLATE/bug-report.md` with these headings in order: Problem; Reproduction;
Expected behavior; Evidence; Environment; Scope and privacy. Use
`.github/ISSUE_TEMPLATE/change-proposal.md` with: Problem; Desired outcome; Users and value; Scope and
compatibility; Alternatives; Validation. Keep the shared frontmatter and concise template text
byte-identical across first-party repositories. The issue-template directory contains exactly those
two Markdown files and `config.yml`; keep the config byte-identical as
`blank_issues_enabled: false` followed by one newline.

### Safety, review and releases

Repository and skill workflows default to read-only, offline and bounded behavior. Network access is
explicit, timeouts and result limits are finite, and machine-readable output is preferred at
integration seams. Authentication and account selection are explicit. A mutation states its target
and effect, previews when possible, and requires the authority granted by the current task. Never infer
permission to delete, publish, send, purchase, change credentials or permissions, or alter a service.

Use synthetic fixtures. Never commit credentials, tokens, private identifiers, customer data,
private URLs, transcripts, copied private-project language or owner-specific paths. Sanitize logs and
errors, keep secrets out of arguments and output, and test masking and refusal paths.

Use the shared pull-request template and preserve its headings: Summary; Scope and compatibility;
Critical risk; Validation; Repository gates; Release; Manual user path; Agent. End the Agent section
with `🤖 by <Agent>`, replacing the placeholder with the filing agent's display name. Record exact commands,
counts, install-preview output, compatibility conclusions and privacy review for the exact head
commit. Required CI must pass for that head. After merge, verify the exact merge commit's `main`
workflow before an authorized tag or release.

Bump the catalog version only when published skill, catalog or bundled runtime content changes.
Process-only changes to `AGENTS.md`, `CLAUDE.md`, documentation, issue or pull-request templates, or
workflow wording do not bump it. Removing or renaming a skill revokes or breaks existing grants and
is a breaking change; state the migration and compatibility impact before publication.

## Writing one of your own

Your own skills stand in the `local` catalog, which the install makes and rundesk never fetches
into. It is **flat** — one directory per skill, straight inside it — because nothing is ever fetched
or swapped there, so the `app/skills/` a published catalog needs would be two levels of ceremony in
the one catalog somebody writes into by hand.
Ask where the library is rather than writing a path down — an install can be pointed anywhere:

```sh
rundesk skills                    # prints the library, and everything in it
library=$(rundesk skills | head -1 | sed 's/^skills in //')

mkdir -p "$library/local/release-notes"
$EDITOR "$library/local/release-notes/SKILL.md"
rundesk skills grant alan local/release-notes
```

```markdown
---
name: release-notes
description: How this team writes release notes. Use when asked to draft, review or edit release notes, when a version is being tagged, or when deciding what a change should say to somebody who did not make it.
---

# Release notes

Write for somebody who did not make the change...
```

`name` and `description` are the only frontmatter to use. Other fields exist, they differ between
providers, and one provider silently dropping a skill over a key another accepts is not worth the
trouble. `name` must equal the directory it stands in — a provider indexes it by the directory — and
`description` is the **whole** triggering mechanism, because nothing below the frontmatter is read
until the skill has already been triggered.

The shipped `writing-skills` skill teaches this properly, including what makes a description trigger
and what never belongs in a skill. It is granted from `rundesk/writing-skills`.

## Declaring what a skill needs

A skill that talks to something outside this machine says so, in `rundesk.json` beside its `SKILL.md`.
It has exactly one key:

```json
{
  "needs": {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com"
  }
}
```

A map of environment variable to **why it is needed**. That one field drives the install preview, the
guided `rundesk skills configure`, which profiles exist, every listing and every `doctor` verdict.

The reason is not decoration. It is what somebody reads when `rundesk skills doctor` tells them a value
is missing, and the only thing that says where to go and get one. A skill with no `rundesk.json`
declares nothing, needs nothing, and is never reported as blocked.

**Never put a credential in a skill.** Name the variable; the owner places it with `rundesk env set`.

**Declare the plain names, and profiles come for free.** An owner with three Jira sites sets
`JIRA_API_TOKEN__ACME`, `JIRA_API_TOKEN__BETA` and so on, and rundesk finds those accounts from the
names you declared. A profile carries all of its own values or it is reported incomplete, so nothing
you write has to handle a half-configured one.

Values are declared **in the order you write them**, and `configure` asks for them in that order — put
the site before the token, the way a person would set it up.

### What is deliberately not in this format

| Not here | Why |
|---|---|
| a `skills` list in the manifest | skills are found by walking `skills/`; a list is a second thing to keep in step with a directory |
| `optional` | declare what is required. A value your script uses if it happens to be there is your business, and `SKILL.md` is where you say so |
| per-script needs | one declaration per skill. Two granularities is two ways to be inconsistent |
| a profile declaration | profiles are found from what is stored, so adding an account needs no edit to your catalog |

One required file with four fields and one optional file with one field is the whole contract. That is
the amount somebody can still hold in their head in a year, which is the point.

## Declaring an OAuth provider

A catalog whose skills sign in to something — rather than being handed an API key — puts one more
optional file beside a `SKILL.md`: `oauth-provider.json`. It is **data, never code**: rundesk reads
it, validates every field against a closed schema, and executes nothing a catalog ships. That is
what lets rundesk gain a provider without gaining a line of provider-specific code, and it is why
`rundesk login` knows no vendor names.

```json
{
  "schema": 1,
  "provider": "example",
  "display_name": "Example",
  "authorization_endpoint": "https://identity.example/authorize",
  "token_endpoint": "https://identity.example/token",
  "identity_endpoint": "https://identity.example/me",
  "base_scopes": ["identity"],
  "identity": {"subject": "sub", "email": "email", "email_verified": "email_verified"},
  "authorization_parameters": {"prompt": "consent"},
  "client_secret": true,
  "capabilities": {"read-reports": "reports.read"}
}
```

Every key is required and no other key is allowed. What each one has to be:

| Field | What it must be |
|---|---|
| `provider`, every capability key | a lowercase hyphenated identifier, at most 64 characters |
| the three endpoints | HTTPS, with no embedded credentials, **no query string and no fragment** |
| `base_scopes` | 1 to 32 non-empty strings that establish a verified immutable subject and email |
| `identity` | exactly `subject`, `email` and `email_verified` — the field names *that provider* uses |
| `authorization_parameters` | at most 32 string values the provider requires; none of `client_id`, `redirect_uri`, `response_type`, `scope`, `state`, `code_challenge`, `code_challenge_method` |
| `client_secret` | a JSON boolean: whether this provider's Desktop app has one |
| `capabilities` | 1 to 64 entries, each mapping a capability name to exactly the one extra scope its integration needs |

A query or fragment on an endpoint is refused rather than merged, so that building the
authorization URL stays unambiguous; a provider that genuinely requires an extra parameter has
`authorization_parameters` for it. Any single string is bounded at 1,024 characters and the whole
file at 64 KiB — a declaration is untrusted input from a repository somebody installed.

**Exactly one skill on an install may declare a given provider ID.** Two that do make *both*
unusable rather than letting the walk order decide which one a credential is handed to.

Two failure boundaries, deliberately different:

- **Installing** a catalog whose declaration is malformed is refused outright, along with the rest
  of the install. That is where strictness costs nothing.
- A malformed declaration **already on disk** makes only its own provider unusable. Every other
  provider still works, and `rundesk login <unknown>` names which declarations could not be read.
  One catalog's typo used to make every provider on the machine unreachable.

A grant is pinned to the fingerprint of the fields above that decide *behaviour* — endpoints,
scopes, identity fields, parameters, capabilities — so a declaration that changes underneath an
install is refused until somebody reviews it and reconnects. `display_name` is deliberately outside
that fingerprint: correcting a capitalisation should not make an owner reconnect every account.

The provider ID also decides what the app client is called: `example` gives
`EXAMPLE_OAUTH_CLIENT_ID` and `EXAMPLE_OAUTH_CLIENT_SECRET`, which an owner places with
`rundesk env set` before signing in. Document exactly those two names in your skill, alongside the
four things a person has to get right and which are easy to confuse: the **APIs** to enable, the
**consent-screen scopes** the app requests, the **permissions the signing-in person already holds**
on the resources, and the **account and resource** a command selects at run time.

Skills consume a declared provider through rundesk's private bridge rather than by handling tokens.
See `docs/commands.md` for the socket protocol, and the bundled `writing-skills` skill's
integrations reference for the caller's side of it.

## The catalog rundesk ships

One catalog does not come from a repository at all. `rundesk` is part of the release, kept as source
beside the provider and channel adapters, and pre-installed on every machine:

```text
src/skills/                       in the release — what a checkout holds
├── manifest.json
├── managing-github/SKILL.md
├── managing-rundesk/SKILL.md
└── writing-skills/SKILL.md
```

| Where | Whose it is |
|---|---|
| `paths.code()/skills/` — an install's `app/src/skills/` | part of the release, replaced whole by an update |
| `data/skills/rundesk/` | where it is installed to, like any other catalog |

**The skills stand beside the manifest rather than one level down.** A catalog *on disk* keeps its
skills in a `skills/` directory, and holding that shape in the release would read
`src/skills/skills/<name>/`. Rundesk puts that level in on the way in, so the directory somebody
opens lists the skills — and what gets installed still goes through the same validation and the same
swap a catalog fetched from GitHub gets, because it is not worth having one catalog this product
reads a special way.

**It is replaced out of the release on every install and every update**, whether or not the release
moved — so a skill edited in place, or deleted, is put back. It is the product-owned operating
catalog: version-coupled Rundesk guidance and first-party delivery workflows have one canonical
source in the CLI instead of being borrowed from a general catalog.

## Publishing a catalog

A catalog is a repository with `manifest.json` at its root and `skills/` beside it:

```text
acme-skills/
├── manifest.json
└── skills/
    ├── release-notes/
    │   └── SKILL.md
    └── jira/
        ├── SKILL.md
        ├── rundesk.json
        └── scripts/search.py
```

```json
{
  "schema": 1,
  "name": "acme-skills",
  "version": "1.2.0",
  "description": "Skills for working on Acme's systems."
}
```

`name` must be usable as a directory name; `version` is shown to people; `schema` is the contract
version and this release accepts `1`. A manifest declaring any other schema is **refused rather than
read hopefully** — a field this release has never seen might be the one saying where the skills are,
and a hopeful reading installs an empty catalog while reporting success.

**Which skills it holds is found, not listed.** Every directory under `skills/` with a `SKILL.md` in
it. Adding one is a directory appearing.

A manifest carrying a `skills` list is still read — the published `rundesk-skills` catalog has one,
and rundesk ignores it rather than refusing it. Nothing is gained by keeping one in step with the
directory beside it, which is the whole reason the list stopped being the answer.

A catalog holding **no** skills is refused. A repository pointed at the wrong branch would otherwise
install in silence, and the symptom arrives days later as an agent that does not know something.

A catalog holding a skill no provider would load is refused too, and **every** such skill is named
rather than the first — a refusal naming one is a refusal somebody fixes and meets again.

## Installing it

```sh
rundesk skills install https://github.com/acme/acme-skills            # says what it would do
rundesk skills install https://github.com/acme/acme-skills --confirm
```

Two kinds of source and no others: a **GitHub repository URL**, or a **directory on this machine**. The
directory is how you work on a catalog before publishing it, and it is why the whole of rundesk's own
test suite runs with no network:

```sh
rundesk skills install ./acme-skills --confirm
rundesk skills update acme-skills --confirm
```

A repository may also declare a Rundesk team. Installing it through `skills install` installs only
the skills: no agent is created or reconciled, and the catalog follows ordinary skill update and
removal behavior. Installing it through `teams install` installs the same skills plus the guarded
team lifecycle. A later `teams install` promotes the skills-only catalog in place, so users can
start with the skills and add the declared team without removing or duplicating the catalog.

If your catalog is not on GitHub, clone it yourself and point rundesk at the clone. Every source shape
accepted here is one rundesk has to keep fetching correctly for ever, so there are two.

## How an update decides there is something to do

**What is on the far end is authoritative, and the version decides nothing.** A catalog whose author
edited a skill without bumping a number is still one this install should be running.

So the far end is asked, cheaply: the `ETag` from the last fetch goes back out as `If-None-Match`, and
a catalog nobody has touched answers `304` with no body at all. When something has changed, the whole
tree is replaced.

**A tree that comes back identical to the one already installed is not a change**, and this is what
makes a local directory usable as a source while you are writing a catalog. A directory has no `ETag`
to be conditional with, so it hands back everything it has every time you check it — and treating that
as a change would mean every check reported replacing a tree, having replaced it with a copy of itself.
What is compared is the content of the whole tree, so this is the same rule as everywhere else here:
content decides. The `ETag` is still written down, so the next check over HTTP is one conditional
request rather than another whole download of something you already have.

`rundesk skills update <catalog>` without `--confirm` previews using that same comparison, so what it
says would happen is what `--confirm` does.

**A local edit inside a catalog is discarded, and that is the feature.** The repository is the source
of truth, so replacing the tree also repairs a skill somebody edited in place — which is what keeps
every machine running the same thing. To change a catalog skill, change it where it is published, or
copy it into `local` under a new name.

A skill that disappears from a catalog is **revoked from every agent holding it**, and each is named:
a grant pointing at a skill that is not there is a link every provider skips in silence, so the agent
would go on being described as holding something it cannot use.

## When it goes wrong

| It says | It means |
|---|---|
| `there is no manifest.json at the top of what was fetched` | the repository root has no manifest, or the archive has more than one directory in it |
| `declares no skills` | nothing under `skills/` holds a `SKILL.md` |
| `holds N skill(s) that cannot be used` | each one is named, with what is wrong: a frontmatter name that does not match its directory, a missing description, or a `rundesk.json` that will not parse |
| `is already installed` | use `rundesk skills update <catalog>` |
| `calls itself X and this install has it as Y` | the manifest was renamed; install it under the new name and remove the old |
| `is the catalog that ships inside the release` | you cannot install a catalog called `rundesk`; it comes out of the release |

`rundesk skills doctor` is the other half of this: it says which granted skill cannot be used, which
account, which value, and the one command that fixes it.
