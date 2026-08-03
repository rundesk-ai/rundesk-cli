# Writing a role

A role is a specialist execution definition: what the specialty is, and the rules one run of it
follows. Every named agent on this install may put it on. **A role is two files in a directory**,
and it is a role the moment both are there — `rundesk roles add` writes that pair for you.

## Making one

```sh
rundesk roles add <slug> \
  --description "<one sentence naming what it answers for and how heavy the work is>" \
  --skills <a,b,c> \
  --posture read|work
```

**It names no agent, and that is the point.** A role is the install's — written once, and every
named agent on it may put it on — so there is nobody to name. The agent stays where it means
something: `rundesk roles <you> run <slug>` and the other four verbs about a *run*, which
belongs to the agent that admitted it.

`--description`, `--skills` and `--posture` are all required. Posture especially: it is a real
safety narrowing, so nothing here picks the widest boundary on your behalf. `--provider` and
`--model` are the optional pair, and a role that names neither runs on whatever its parent turn
resolved.

It **refuses rather than overwriting**. A slug that is already a role, a directory holding only
one of the two files, a posture that is not one, a skill named twice, a description past the
limit — each is a refusal that changes nothing on disk, and each says the whole reason.

Then read what it answered with. It prints the absolute path of the `AGENTS.md` it wrote, and
that file is **a generic skeleton and is not yet about your specialty**: every section in it is a
`TODO` addressed to whoever is writing the role. Rewrite it before the role is handed real work.
A role run against the unedited skeleton does not fail loudly; it returns a report that reads
well and is about nothing.

## Where they stand

Beside the agents rather than beside the program, so ask rather than writing a path down — which
is what `add` is doing for you, and worth knowing when you are reading an unfamiliar install:

```sh
roles="$(dirname "$(rundesk agents <you> | awk '$1=="agent"{print $2}')")/.roles"
mkdir -p "$roles/<slug>"
```

`rundesk roles` lists what is installed, and `rundesk roles <you>` lists the same with your own
role runs beneath it. A directory missing either file is not listed and
has broken nothing — half a role is invisible, not fatal. `add` is the one place that says so out
loud: asked for a slug standing as half a role, it names the file that is missing and why nothing
of that name is usable.

## The two files

```text
<slug>/
├── role.json     description, skills, posture — and nothing else
└── AGENTS.md     the rules one execution follows
```

Everything else is derived, so there is nothing to keep true: the slug is the directory name, the
display label is the slug read aloud (`code-review` becomes `Code Review`), and the revision is a
digest of the manifest, the rules and every skill it exposes. **Never add a version field.** The
manifest is a closed set of three keys and a fourth is refused outright, because a setting nobody
reads is one somebody believes is deciding what an isolated execution may do.

```json
{
  "description": "Answer one bounded question from evidence — every claim sourced, nothing changed.",
  "skills": ["python-patterns", "python-testing"],
  "posture": "read"
}
```

- **`description`** — one sentence, 1024 characters at most. It is what a named agent reads when
  deciding whether to delegate at all, so it says what the role answers for, not how it works.
- **`skills`** — at least one, each lowercase letters, digits and single hyphens. No duplicates:
  two entries of one name is refused rather than collapsed. A name this machine has no skill for
  is left out and reported as missing rather than refusing the role, so a definition can be
  shared between machines — but the run then does less than the description implies.
- **`posture`** — `read` or `work`, and nothing else. `read` is a real narrowing: on some brains
  it is a read-only sandbox, and on others it is an allowlist with **no shell in it at all**, so a
  `read` role cannot run `git log`, run a test, or write a scratch file. Choose it when the role's
  guarantee is that it changed nothing, and say in its rules that a refused command is evidence
  missing rather than something to route around. A role may narrow what its parent could do and
  can never widen it.

## The rules file, in this order

Every role uses the same skeleton, so a parent reading an unfamiliar one finds the ceiling and
the definition of done where they were in the last one. This is the same skeleton `add` writes,
and a test holds the two to the same headings — so what is below is what you will find in the
file, not a second description of it:

```markdown
# <Label>

<what this role answers for, and that the project's own instruction files beat these rules>

## Start here, in this order     the brief and any plan, then the project's rules, then skills —
                                 ending in what the run settles before it starts
## While you work                the few rules this specialty gets wrong without being told,
                                 ending in two bullets every role holds — the ceiling this one
                                 narrows to, and what a subagent is worth here
## The report                    the named sections the parent is owed
## Definition of done            numbered, checkable, and last
```

Rundesk puts its own floor above your rules and the run's mechanics below them, so **never
restate either**: that the worker is not a named agent, has no memory, may not answer anybody,
may not operate Rundesk and may not start another role is already said, as is the run id, the
target and where non-project files go. A copy is the same words paid for twice and a second
place to be wrong.

Write the specialty instead — the things this kind of work gets wrong. Explain why: `do X,
because Y tends to cause Z` survives pressure that `ALWAYS DO X` does not.

**Name the weight of the work, in the opening line.** A run costs a whole context to set up and
hands back one report a parent has to review, so a role earns its place on work heavy enough that
the parent could not simply have done it — a change too large to hold, a sweep across hundreds of
sites, a subsystem that has to be held in view all at once. Say which of those this one is, in the
`description` a parent reads while deciding whether to delegate and again in the first lines of
the rules. A role described by its subject rather than its weight is one that will be handed
two-file edits.

## The definition of done is the point

A role's report is unchecked work, and Rundesk asserts nothing about it. The definition of done
is what the parent reviews against, so write it as numbered claims somebody who was not there
can check:

- ✅ `The command that proves it was run and its output is in the report — a failure verbatim.`
- ❌ `Make sure the work is properly tested and high quality.`

Every one of them ends with the same last item, whatever the specialty: **the report is true
about what you did not do.** Undone work reported as done is the one failure that costs more
than the task.

## Editing one

The manifest is a command. The rules are a file you open yourself.

```sh
rundesk roles edit <slug> \
  --description "<what it answers for>" \
  --skills <a,b,c> \
  --posture read|work \
  --provider <provider> \
  --model <model>
```

Every flag is optional, and **a field no flag names keeps exactly what it says now**. Three
things about that are worth knowing before you type it:

- **`--skills` replaces the whole set.** There is no add and no remove — name every skill the
  role is to have. Passing the one you meant to add leaves the role holding only that one.
- **An empty value is a decision, not a spelling of "left out".** `--provider ""` unpins a
  brain and takes the field out of the file, so the role goes back to running on whatever its
  parent turn resolved — and back to the revision it had before anybody pinned one.
- **Naming no field at all is refused.** An edit that changed nothing would otherwise report
  success for a command that did nothing.

It changes the manifest **whole or not at all**, and **refuses a manifest it cannot read**
rather than rewriting it: a field this release has never heard of is one you put there, and
overlaying onto it would discard it in silence. What it answers with is what actually *moved*,
field by field, and the revision it moved from and to — which is the word a run's locked bytes
are identified by afterwards.

**It never touches `AGENTS.md`.** The rules are prose you wrote, and a specialty that has moved
is yours to bring in line — open the file the answer names. Both files are equally editable by
hand; the command is the shorter route to one of them, and writing the manifest yourself is
still fine as long as you write the whole of it.

An edit lands on the **next** run. Every run locks its own copy of the rules, the manifest and
every skill package before the brain starts, so a run in flight and a run resumed a fortnight
later both keep the bytes they were admitted with, and the revision recorded against them says
which. Edit freely while work is running; nothing in flight changes under it.

Two gotchas about the roles this release ships, and `edit` is now the easiest way to trip the
second of them:

- **An update never replaces a role that is already there**, edited or not. A new release's
  version of a shipped role reaches only an install that has not got one of that name.
- **One character different and the role is yours.** What proves a role is still Rundesk's is
  that it is still byte for byte what Rundesk wrote, so an uninstall leaves an edited one
  standing. Copy a shipped role to a new slug rather than editing it in place when you want both.
  Editing one says so where you can read it, once, and it is not reversible by editing it back.

## Proving it works

Read the rules back as the worker will get them: the floor, then your file, then the mechanics.
Anything that reads as advice to a colleague who already knows the situation is a line that will
be skipped.

Then hand it a small real task with `rundesk roles <you> run <slug>` and review the report
against the definition of done, item by item. **A bad role does not fail loudly** — it returns a
report that reads well and is not true. What you are testing is whether the report contains what
the definition of done demanded, not whether it sounds finished.
