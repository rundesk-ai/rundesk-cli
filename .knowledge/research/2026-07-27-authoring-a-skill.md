# Research: what makes a SKILL.md a model actually triggers and uses correctly

**Last updated:** 2026-07-27
**Question it answers:** What are the durable rules for writing a skill, so that our own guide and our shipped skill-writing skill teach what the field already knows rather than what we guessed?

## What they do

Four independent bodies of guidance exist: Anthropic's published authoring best practices[1], the
`skill-creator` skill OpenAI ships inside Codex[2], the vendor-neutral guidance on the Agent Skills
site[3][4][5], and Anthropic's own shipped `skill-creator` and `skill-development` skills[6][7]. Claude
Code's reference documentation[8] and the Grok CLI's shipped guide[9] add limits and a small number of
rules each. Where they agree, they agree closely enough to quote.

### The description is the entire triggering mechanism

Every source states it. The body is loaded *after* triggering, so a "when to use this" section in the
body cannot help the model decide to use it: "Include all 'when to use' information here — not in the
body."[2] The vendor-neutral guidance puts it as "the description carries the entire burden of
triggering".[4]

The canonical shape states both what the skill does and the contexts that should trigger it — for
example, extracting text and tables from PDFs, "Use when working with PDF files or when the user mentions
PDFs, forms, or document extraction."[1] Anti-examples named in three sources independently are
"Helps with documents" and "Processes data".[1][3][7]

Descriptions should be deliberately pushy, because models under-trigger rather than over-trigger: "Claude
has a tendency to 'undertrigger' skills… make the skill descriptions a little bit 'pushy'", listing
contexts even where the user does not name the domain directly.[6] The vendor-neutral guidance says the
same, in the same words: "Err on the side of being pushy."[4] The description should be phrased toward
the user's intent rather than the implementation, kept to roughly 100–200 words, and made distinctive
because it competes with other skills for attention.[6]

Two sources note that a simple one-step request will not trigger a skill however good the description is,
because a model only consults skills for tasks it cannot easily do alone.[4][6]

### Hard limits, and a small closed frontmatter

`name` is at most 64 characters, lowercase letters, digits and hyphens only, and must match its parent
directory. `description` is at most 1024 characters and non-empty.[10] Both shipped validators enforce
exactly this set of fields — `name`, `description`, `license`, `allowed-tools`, `metadata` — and Codex's
guidance says flatly "Do not include any other fields in YAML frontmatter."[2]

Bodies are kept under 500 lines or roughly 5,000 tokens, stated identically across four sources[1][2][8][10];
one tightens it to 1,500–2,000 words ideal.[7] Claude's reference adds the reason: once a skill loads, its
content stays in context across turns, so every line is a recurring cost.[8]

### Progressive disclosure, in three levels

Metadata always loaded, body on trigger, bundled resources on demand — with scripts effectively free
because they execute without entering context.[1][2][3] The directory convention is universal:
`scripts/` executed, `references/` read on demand, `assets/` used in output and never read.[1][2][3][7]

Two rules attach to splitting. A reference must be introduced by **when to read it** — "Read
`references/api-errors.md` if the API returns a non-200 status code" rather than "see references/ for
details".[3] And references stay one level deep from `SKILL.md`, because a model reading a file
referenced from another referenced file may preview rather than read it and act on incomplete
information.[1] Content must never be duplicated between body and reference: "Information should live in
either SKILL.md or references files, not both."[2][7]

### Write for a model that is already capable

"Default assumption: Codex is already very smart. Only add context Codex doesn't already have."[2] The
vendor-neutral form is a test: would the agent get this wrong without this instruction? If not, cut
it.[3] The same worked example — a short PDF instruction beating a long one — appears in three sources.

Related and equally consistent: give a default rather than a menu of libraries[1][3]; match the degree of
freedom to how fragile the task is, from prose heuristics through parameterised scripts to an exact
command that must not be modified[1][2][3]; favour procedures that teach how to approach a class of
problem over declarations about one instance[3]; and keep one coherent unit of work per skill, since too
narrow makes several load and conflict while too broad cannot activate precisely.[3][9]

### Voice

The body is written in imperative or infinitive form, verb first — "To accomplish X, do Y" rather than
"You should do X".[7][2] The description is written in the third person, because it is injected into a
system prompt and an inconsistent point of view causes discovery problems.[1] The vendor-neutral guidance
appears to conflict, asking for imperative phrasing in the description too ("Use this skill when…").[4]
Both are satisfied by writing toward the agent and never about a speaking assistant.

Explaining why beats commanding: "If you find yourself writing ALWAYS or NEVER in all caps… that's a
yellow flag — if possible, reframe and explain the reasoning."[6] Reasoning-based instructions outperform
rigid directives.[5]

### What a skill must not contain

The sharpest rule found, and unique to Codex's guidance: a skill contains only what an agent needs to do
the job. No `README.md`, no `INSTALLATION_GUIDE.md`, no `QUICK_REFERENCE.md`, no `CHANGELOG.md`, and no
account of the process that created it — "Creating additional documentation files just adds clutter and
confusion."[2]

Anthropic's shipped skill adds a "principle of lack of surprise": a skill's contents must not surprise a
user relative to its description.[6]

### The highest-value content is the gotcha

Environment-specific facts that defy reasonable assumptions — rows that are soft-deleted so every query
needs a predicate, one identifier spelled three ways, a health endpoint that answers while the database
is down. These belong in the body rather than a reference, because a model may not recognise the trigger
to go and read the reference.[3]

### Testing

Build the evaluations before writing extensive documentation, and at least three of them.[1] Always run a
baseline **without** the skill, so a pass proves the skill and not the model.[5] Codex adds a
forward-testing protocol that is unique and specific: test with subagents that do not know they are
testing, prompting "Use $skill-x at /path to solve problem y" rather than "review this skill and
pretend"; pass raw artefacts rather than conclusions; never show the expected answer; use fresh threads;
and if it only passes when the tester has seen leaked context, tighten the skill.[2]

Where the same helper code is rewritten on every run, bundle it as a script instead — detected by reading
execution traces rather than outputs.[2][6]

## What we can borrow

- The whole Tier-1 set above, which is agreed by three or more independent sources: description carries
  triggering, the closed frontmatter, the size limits, the three-level disclosure, the directory
  convention, when-to-read for every reference, no duplication, assume a capable model, degrees of
  freedom, defaults over menus, and test with a baseline.
- **Codex's "what not to include" list**, which nobody else states and which prevents the most common
  bloat.[2]
- **Codex's forward-testing protocol** — a tester who knows it is testing proves nothing, which is the
  same lesson this repository already paid for in a different form.[2]
- **The gotchas section as the highest-value content**, and the reason it stays in the body.[3]
- The mechanical validator shipped beside Codex's skill-creator encodes the naming and frontmatter rules
  in about a hundred lines; rules that are checkable are cheaper checked than written as prose.[2]

## What to avoid

- Writing a "When to use this skill" heading in the body. It is the single most common wasted section:
  by the time it is read, the decision it describes has already been made.[2]
- Inventing frontmatter fields. The closed set is what every loader accepts, and a field one brain
  tolerates is a field another may reject.[2]
- Walls of capitalised MUST and NEVER, which read as a yellow flag that the rule was never explained.[6]
- Shipping a `README.md` inside a skill.[2]
- Time-sensitive statements in a body that nothing will come back to update.[1]
- Judging a skill by whether the model produced a nice answer. Without the baseline run, a pass says
  nothing about the skill.[5]
- Writing evaluation prompts a model would satisfy anyway: a trivial one-step request will not trigger a
  skill however good the description.[4][6]

## Verdict for us

**Adopt the agreed set as our own guide rather than authoring a house theory.** The rules above are
consistent across four independent bodies of guidance and are already what every brain we ship behind is
tuned for. Our guide's value is in the small number of things it adds: how a skill reaches a rundesk
agent, what our own layout is, and the one thing every source leaves open — how to decide what is core
when a body genuinely exceeds the size limit.

**The shipped skill-writing skill teaches this set and our placement.** It is the first built-in, and it
is what makes an agent able to write skills for itself. It must itself obey every rule it teaches, which
is the cheapest possible test of whether the rules are teachable.

**Testing a skill follows Codex's protocol, adapted.** A baseline run without the skill, a canary fact
only the skill can supply, and a tester that does not know what answer is expected. This repository has
already paid for the general form of that lesson twice.

Feeds the skills guide and the first shipped skill; the placement mechanism itself is
[the discovery note](./2026-07-27-skills-a-brain-discovers.md).

## Open questions

- What to do when a body exceeds the size limit and the content is genuinely all core. One source says
  "add a layer of hierarchy" and none says how to choose what moves.[2]
- Whether description quality is worth measuring the way one source does, with a train and validation
  split over twenty queries and selection by validation score.[4] It is a real method and it costs real
  turns.
- Whether our own shipped skills should carry `metadata` naming their origin, or stay bare.

## Sources

1. Anthropic — skill authoring best practices — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
2. The `skill-creator` skill shipped inside the Codex CLI, at `skills/.system/skill-creator/` in its home — (internal)
3. Agent Skills — skill creation best practices — https://agentskills.io/skill-creation/best-practices
4. Agent Skills — optimizing descriptions — https://agentskills.io/skill-creation/optimizing-descriptions
5. Agent Skills — evaluating skills — https://agentskills.io/skill-creation/evaluating-skills
6. The `skill-creator` skill shipped in Anthropic's official plugin marketplace — (internal)
7. The `skill-development` skill shipped in Anthropic's `plugin-dev` plugin — (internal)
8. Claude Code — Skills — https://code.claude.com/docs/en/skills
9. The Grok CLI's own shipped skills guide, `docs/user-guide/08-skills.md` inside its home — (internal)
10. Agent Skills — specification — https://agentskills.io/specification
