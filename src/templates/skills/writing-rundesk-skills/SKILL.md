---
name: writing-rundesk-skills
description: How to write a skill for a rundesk agent and put it in this machine's library so agents can be granted it. Use whenever anyone asks to write, create, author, improve, fix, review or debug a skill for a rundesk agent, or asks why one is not being picked up — and whenever a repeated procedure here looks worth keeping, even if the word "skill" is never said.
---

# Writing a skill

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version
of your own, copy it under a different name — that copy is yours and is never touched.*

A skill is one portable folder. `SKILL.md` is its only required entry; scripts, references,
assets and other resources needed to do the work belong beside it in that same folder. A
brain reads the **description** on every turn and loads the **body** only when it decides
the skill applies. Write for that: the description decides whether the skill is ever used,
the body decides whether it helps.

## Where a skill lives

Every skill on this machine is in one library. **Ask where it is rather than assuming** —
an install pointed somewhere else keeps its skills there too, so a path written down is
wrong on some machines:

```sh
library=$(rundesk skills --where)
mkdir -p "$library/<name>"
$EDITOR "$library/<name>/SKILL.md"
rundesk skills grant <agent> <name>
```

`rundesk skills` lists what exists and who has what. Nothing is placed for an agent until
it is granted, and granting is a link — so editing the library edits what every agent
holding that skill reads, with nothing to re-run.

## The package shape

Follow the Agent Skills directory format:

```text
<name>/
├── SKILL.md          required metadata and instructions
├── scripts/          optional executable helpers
├── references/       optional material loaded only when needed
├── assets/           optional templates and static resources
└── ...               other files the skill needs
```

The whole directory is the skill. Rundesk lays down, grants, updates, backs up and presents
that directory together; do not put a companion command in the shared script library.

`SKILL.md` begins with:

```markdown
---
name: release-notes
description: How this team writes release notes. Use when asked to draft, review or edit
  release notes, a changelog, or a version announcement.
---

# Release notes

<the body>
```

`name` and `description` are the only frontmatter to use. Others exist, they differ
between brains, and one brain silently dropping a skill because of a key another accepts
is not worth the trouble.

- `name` matches the folder exactly: lowercase letters, digits and single hyphens, 64
  characters at most.
- `description` is one or two sentences and never more than 1024 characters.

## The description is the whole of what triggers it

This is the part most worth getting right, and the most common thing to get wrong.

**Say what it does and when to use it.** A brain matches on the *when*.

- ✅ `Extract text and tables from PDFs, fill forms, merge documents. Use when working with PDF files or when someone mentions PDFs, forms or document extraction.`
- ❌ `Helps with documents.`

**Lean pushy.** Brains under-trigger far more often than they over-trigger. List the
situations that should reach for it, including ones where nobody names the topic outright
— "even if they do not say the word 'invoice'".

**Never put "when to use this" in the body.** The body is read *after* the decision it
would inform has already been made. It is the single most common wasted section.

## Writing the body

**Assume the model is already capable.** Before every line, ask: would it get this wrong
without this? If not, cut it. A skill is what it does not already know — your conventions,
your systems, the things that are true here and nowhere else.

**Gotchas are the most valuable thing you can write.** Facts that defy a reasonable
assumption earn their place ahead of anything else:

- rows are soft-deleted, so every query needs `WHERE deleted_at IS NULL`
- the same id is `user_id` in one table, `uid` in another, `accountId` in the API
- `/health` answers 200 while the database is down

Keep those in the body. A model cannot know to go and read a file about a trap it does not
know exists.

**Give a default, not a menu.** "Use X" beats "you could use X, Y or Z" — the choice costs
tokens and invites the wrong one.

**Match how firmly you write to how fragile the task is.** A judgement call gets a
heuristic. Something with one correct sequence gets the exact commands and a note that
they are not to be varied.

**Explain why.** `Do X, because Y tends to cause Z` outperforms `ALWAYS DO X`. Capitalised
absolutes are usually a sign the reason was never written down.

**Write instructions, not prose about the skill.** "To release, run …" rather than "You
should run …" or "This skill helps you …".

## Size, and splitting

Keep the body under 500 lines. Once a skill loads, it stays in context for the rest of the
conversation, so every line is a cost paid repeatedly.

When it genuinely will not fit, put the overflow in `references/` beside the `SKILL.md`
and **say when to read each file**:

- ✅ `Read references/api-errors.md when the API returns anything other than 200.`
- ❌ `See references/ for more detail.`

Keep references one level deep — a file reached from another referenced file may be
skimmed rather than read, and acted on half-known. Never put the same thing in both the
body and a reference; one of the two will drift.

Repeated helper code belongs in `scripts/` beside the skill, not pasted into the body.
Keep commands self-contained and executable, give each a credential-free `--help`, and
keep offline tests beside their implementation. Credentials never belong in the package;
name the environment variable or owner-only configuration file the command reads.

An agent turn receives its granted skills directory as `RUNDESK_SKILLS`. Invoke a bundled
command through that provider-independent path:

```sh
"$RUNDESK_SKILLS/<name>/scripts/<command>" <arguments>
```

Use that path in examples. Do not rely on the current working directory, an owner-specific
absolute path, or a duplicate launcher in `rundesk scripts --where`.

Output templates, images and other files used to produce a result belong in `assets/`.
Say exactly when to use each one; an asset is not reference material to load into context.

## What never goes in a skill

- `README.md`, `CHANGELOG.md`, installation notes, or any account of how the skill was
  made. A skill holds what an agent needs to do the job and nothing else.
- Credentials, tokens, or anything secret. Name the environment variable instead.
- Absolute paths that are only true on one machine.
- Anything already in `AGENTS.md`, `SOUL.md` or `MEMORY.md` — those load every turn, so a
  copy here is the same words paid for twice and a second place to be wrong.
- Dated statements nothing will come back and update.

## Proving it works

**Run it without the skill first.** If the answer is already right, the skill is not
needed — and without that baseline a pass tells you nothing about whether the skill did
anything at all.

Then give an agent the skill and ask the same thing, in the words somebody would really
use, without mentioning the skill. Ask for something only the skill can supply.

Two traps worth knowing:

- **Never ask a question the conversation has already answered.** The model will answer
  from earlier in the thread and the skill will look like it worked. Use a fresh session.
- **A trivial one-step request will not trigger any skill**, however good the description.
  Brains only reach for a skill on work they cannot easily do unaided, so test with a real
  task.

If it does not fire, the description is nearly always the reason. Widen the situations it
names before touching the body.
