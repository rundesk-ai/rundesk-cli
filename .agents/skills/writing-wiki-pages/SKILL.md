---
name: writing-wiki-pages
description: Use when writing, updating, reviewing or fixing the pages of a wiki that the `wiki` command builds and checks — a folder holding `wiki.toml` and `pages/` — including a new page, a page the code has moved on from, a stated requirement not built yet, a failing `wiki check`, pages to organize or restructure, or the name or wording of a page, a heading or a label a reader sees there. It supplies the page contract, citations, naming, voice, and the steps for each of those tasks. Do not use for documentation written for builders, such as a README, codemap or contributing guide.
---

# Writing wiki pages

**Read [Page standard](references/page-standard.md) before writing a page or restructuring one.** It holds
a page written to the standard, the same content written badly, and why the difference matters. Rules say
what to avoid; only an example shows what good looks like. A page written from these rules alone comes out
**flat, true and unread** — the failure this skill exists to prevent, and a failure that does not announce
itself.

**The wiki is written for four readers, in words each of them can follow.** They are the stakeholders and
the product owner, who decide what the system is for; the engineering team, who build and change it; and,
in some wikis, its customers. None of them should need to read code to learn what the system does, and a
page that only an engineer can follow is unusable to the stakeholders, the product owner and the
customers. Every rule below serves one job:
**each reader sees how the system works without reading the code.**

Nothing here is specific to one project. These rules travel with the wiki into any project that installs
it.

## Tasks

Find the task, follow its steps, and apply the sections below as each step needs them. Run `wiki` through
the project's wrapper script if it has one. A change of a few words — a label, a heading, one sentence —
needs [Naming and grammar](references/naming-and-grammar.md) rather than the page standard.

### New page

1. Read [Page standard](references/page-standard.md). For a command, endpoint, published function, event,
   settings file or form, read [Reference pages](references/reference-pages.md) and
   [Reference standard](references/reference-standard.md) too. When the page's siblings are the same kind
   of thing as it, read [Page families](references/page-families.md) and write to the layout they share.
2. Read the code the page describes. Every statement comes from it, the stated requirements, or an
   outside service's own documentation.
3. Write the intent first, from the stated requirements, set `status = "draft"`, and ask for approval.
4. Put the file where it nests, cite every sentence, and add a row to any page that lists its siblings.
5. Run `wiki check`, then the self-edit at the end of Page standard.

### Change in the code

1. Find the pages the change affects: search the pages for each changed file's path, and for each name
   the change touched that a person uses, such as a command, option or setting.
2. Read each sentence that cites the changed code against the code as it is now, and correct both what the
   sentence says and what its reference names.
3. Give each new thing a person can use, configure or notice its page or a section, in the same change.
4. Replace each `{missing}` the change implements with a citation to the code that does it.
5. Run `wiki check`.

### Requirement not built yet

1. Write each stated requirement on the page it belongs to, marked `{missing}`, as
   [Missing citations](#missing-citations) describes. A thing not built at all gets its own draft page.
2. Write nothing the stated requirements do not say. List what they leave undecided, and ask for those
   requirements.
3. Run `wiki check`.

### Failing check

1. Read every problem `wiki check` names; each says what to change.
2. Give a sentence with no citation the reference that establishes it, or `{missing}`, or cut it when it
   serves nothing in the intent. A reference that does not establish its sentence is not a citation.
3. Change nothing the problems do not name, and run `wiki check` again.

### Review

1. Read this skill and every reference in full: they are the standard. Report findings, and edit a page
   only when the task asks for fixes.
2. Run `wiki check` and record its result. It proves that every sentence cites something, not that what
   it cites is true.
3. Open every file and function each page cites, and confirm it does exactly what the sentence says:
   numbers, defaults, names, messages and exit codes.
4. Inventory the part of the code under review, as [Coverage](#coverage) describes, and name what no page
   covers. When `wiki.toml` has a `[coverage]` table, start from what `wiki coverage` lists.
5. Report each finding by page and line, with what is wrong and the fix, most severe first: false,
   undocumented, uncited, stale, writing.
6. Run `wiki audit` with every page reviewed that had no finding, leaving out any page that says
   `goals = false`.

### Organization

1. Read [Page families](references/page-families.md).
2. Run `wiki families`, then list every page in the part of the wiki to organize, with its title, intent
   and headings.
3. Group the pages about things of one kind into families, each nested under one parent page.
4. Design each family's layout: the headings every member carries, in order, and the infobox groups and
   labels every member fills.
5. Ask for approval of the families, their layouts and every page that moves, and change nothing until
   they are approved.
6. Move each page, rewrite each member to its family's layout keeping every citation, and give each parent
   its lead, its member table and its `[family]` declaration.
7. Run `wiki check`, which names every link a move broke.

## Wiki structure

You write markdown; the generator writes the site. The wiki is `docs/wiki` unless the project passes
`--wiki`, and `<wiki>` below means that folder.

| Thing | Where | What it does |
|---|---|---|
| A page | `<wiki>/pages/**.md` | TOML front matter between `+++` fences, then markdown |
| Its address | its path | `pages/billing/invoices/refunds.md` is `/billing/invoices/refunds/` |
| Its place | its path | it nests under `pages/billing/invoices.md` in the sidebar |
| The sidebar | `<wiki>/wiki.toml` | sections name only the pages that **start** a branch |
| Pictures | `<wiki>/images/` | with `PICTURES.toml`, recording what each shows |
| PDFs | `<wiki>/files/` | documents a page links; a build publishes only those, at most 20 MB each |
| The site | `<wiki>/site/` | generated, ignored by git, rebuilt before it is served |
| Dates | `<wiki>/UPDATED.toml` | written by the build; a date moves only when its page does, and an audit date only with `wiki audit` |

```sh
wiki serve    # build, serve, open a browser
wiki check    # what the gate runs
```

**To add a page**, put its file where it belongs: a page in a folder named after another page nests under
it. Name it in `wiki.toml` only when it starts a new branch.

## Vocabulary

Use these words in commits, reviews and conversation. They are the generator's.

- **Page** — one markdown file, one address.
- **Intent** — two to four sentences of front matter saying what the thing is *for*. The contract.
- **Lead** — the body's opening paragraph, before any heading.
- **Infobox** — the panel at the top right: **groups** of **rows**, each a **label** and a **value**.
- **Citation** — a numbered mark in the prose. **Reference** — its entry at the foot of the page.
- **Missing citation** — the red mark for a claim with nothing to cite, written `{missing}`.
- **Category** — a cross-cutting label, in the bar at the foot of a page. Not the sidebar.
- **Reference page** — a page for something a person calls or configures: a command, an endpoint, a
  published function, a settings file, a form.
- **Goals page** — every page's intent, collected. Generated, never written.
- **Health page** — every page's status, citations, claims with no source and audit date, written by the
  build onto `health.md` when the wiki has one.
- **Source view** — the Source tab, showing a page's own markdown.
- **Audience** — `internal`, the default, or `user`, which `wiki user` builds.

## Readers

One page is read by four readers, each for a different part of it. **Write each part for the reader who
reads it**, and the page serves all four without being written four times.

| Reader | Reads | Comes for | Written so that it |
|---|---|---|---|
| Stakeholder | the intent, the lead and the goals page | whether the system does what it was meant to | states what the system is for and what it does, in words the stakeholder uses, never function or field names |
| Product owner | the lead, the headings, the infobox and the prose | the system's rules, limits and consequences | states each rule, limit and consequence plainly, with figures a person would notice |
| Engineering team | the prose, the references and the reference pages | the behavior to keep, and where it happens | cites every statement to its file and function, and gives each name the software owns exactly |
| Customer | a page marked `audience = "user"`, built without references | how to use the system, and what to expect from it | describes what the customer does, sees and is refused, and names no product owner, team, agent, branch, function or field |

- **Plain words carry the sentence, and the exact name follows.** Say what happens in ordinary words, then
  give the name a person types or searches for, as code: "A session ends thirty minutes after its last
  request, set by `session.timeout`." The product owner follows the sentence; the engineer searches the
  name.
- **A term is defined where a page first uses it**, in the same sentence, or linked to the page that
  defines it. A word the stakeholders use themselves needs no definition; a word only the engineering team
  uses does.
- **One page, not one per reader.** A stakeholder's version and an engineer's version of one thing drift
  apart: a change reaches one of them and not the other. The intent, the lead, the infobox and the
  references already separate what each reader reads.
- **A page for customers speaks to them.** A page marked `audience = "user"` names no product owner,
  engineering team, agent, branch, function or field, and calls the person using the system "you".

## Intent

Every page opens with an `intent`: what the thing is **for** and what outcome it should produce — never how
it works.

```toml
intent = """
Refunds exist so that a customer who was charged wrongly gets their money back without having to ask
twice. A refund that needs a support conversation has failed. It should be possible to issue one
in seconds and impossible to issue one by accident.
"""
```

- **Every sentence serves the intent.** One that does not is **cut** — not moved, not shortened.
- **Nothing outgrows its intent.** Anything worth saying that the intent does not cover needs its own page
  and an approved intent — or it is engineering documentation and does not belong here.
- **A long page means the intent is too broad.** When every sentence serves the intent and the page still
  runs long, split the intent and nest the new page under this one. Cutting good sentences to hit a
  number makes a worse page.

**Write the intent first.** It decides what the page holds; written last, the page gets written twice.
**An intent is approved before a page is.** Draft it from the stated requirements, mark the page a draft,
and ask for approval; never invent what a thing is for.

## Naming

Naming is most of what makes a page readable, and it goes wrong first. In code a class is a noun and a
function a verb; in an encyclopedia a title is a noun phrase, never a verb or a question. A wiki has no
actions, so **every name on a page is a noun phrase** for a thing a reader wants. The failure is always the
same: the writer names their question instead of its answer.

**Read [Naming and grammar](references/naming-and-grammar.md) before naming a page, a heading or a label, before describing a
name the software owns — a field, an option, a setting — and before the last pass over any page.**

### Method

Find the section by its question; name it by the answer.

| The question | Never call it | Call it |
|---|---|---|
| Where does it live? | "Where it is stored" | **Storage**, **Location** |
| Why is it like this? | "Why it works this way" | **Reasoning**, or the reason itself |
| How does it grow? | "How the cache fills up" | **Growth** |
| How long does it last? | "How long it lasts" | **Expiry**, **Lifespan** |
| What does it accept? | "What it takes as input" | **Input**, **Formats** |
| When does it happen? | "When it runs" | **Schedule**, **Timing** |
| What is it for? | "What it is for" | **Purpose**, **Use** |
| What makes it different? | "Two differences, and only two" | **Differences** |
| Is it any good? | "Fast enough to matter" | the subject: **Speed** |
| What does this file show? | "A worked page" | **Page standard** |

A gerund is a noun and is fine: **Caching**, **Signing out**. A gerund phrase is usually the question in
disguise: "Getting started" wants to be **Setup**.

### Tests for a name

From the encyclopedia's title policy, for titles, headings and categories alike. A name is:

- **Recognisable** — a reader who knows the subject, without being expert in it, knows what this is.
- **Natural** — what they would say aloud, and what another page would link to it as.
- **Precise** — this subject, not a neighbor. "Limits" is a size on a page about uploads and a rate on
  one about the API; the page supplies the subject. **A nested page's title names only what sets it apart
  within its parent**: under **Checks**, a page is **Citations**, not "Citation checks", because the
  sidebar, the trail above the title and search all show the parent.
- **Concise** — no longer than it takes to identify the thing.
- **Consistent** — the same kind of thing named the same way on every page. If one page says **Storage**,
  no page says "Where data is kept".

### Names on a page

- **A page title** is the thing the page is about: **Refunds**, **Sessions**, **Nightly run**. No leading
  "The" unless it is part of the name.
- **A subtitle** is a short description naming the specific things the page covers, in lower case, so a
  reader choosing between pages in search can tell them apart: **word limits for a page, an intent and the
  goals page**, not "how long a page may be". It never opens with How, What, Where, Why or When, never
  lets a vague word stand in for a thing ("and other drawings", "here", "this machine"), and is never a
  slogan ("labels, not questions"). The gate refuses one that opens with a question word. A reference
  page's subtitle is the software's own help line, exactly.
- **A heading** is the same, one level down. It is never a question: "Where it is stored" is the writer
  wondering what belongs there, and the reader wanted **Storage**. It is never a verdict: "Fast enough to
  matter", "Important notes" and "Overview" rate the contents instead of naming them. The gate refuses a
  heading opening How, What, Where, Why or When, and one that rates itself.
- **A category** is a plural noun for a set: **Background jobs**, not "Jobs that run in the background".
- **An infobox label** is a noun phrase naming a property, which the value gives: **Expiry** · 30 minutes.
- **Nothing points; everything is named.** "This site", "Our setup" and "These options" point at the page
  instead of naming the thing: **Domain**, **Setup**, **Options**. In prose, "this repository" or "this
  wiki" means nothing to a reader who arrived from a search: name the part of the system that acts, such
  as the results page, the server or the build, and use the project's name only where no nearer part acts.
  The gate refuses both.

**When no good name exists, the section is wrong, not the name.** A heading that will not fit in two words
is usually two sections, or one that has not decided what it is about.

## Page shape

**Answer first, detail after**, at every level: the lead answers the page, a section's first line answers
the section, a sentence's first clause answers the sentence. A reader who stops early is still right.

- **The lead stands alone.** Whoever reads only the first paragraph gets the true shape of the thing,
  surprising fact included.
- **A heading is a label on a drawer**: it names what is inside, so a scanning reader knows whether to stop.
  One or two plain words is usually right, named as [Naming](#naming) describes.
- **Three to five sections.** More, and the page is two pages.
- **Split rather than swell.** A subject that needs its own treatment becomes a child page and a link, not
  another heading; the sidebar nests it.

## Page families

**Pages about things of one kind share one layout**: the brands under a sites page, the providers under a
payments page, the channels under a notifications page. A reader who has read one member knows where to
look on every other, and compares two side by side instead of searching each page for a fact the others
place elsewhere.

- **The layout is designed once, for the family**: the headings every member carries, in one order, and
  the infobox groups and labels every member fills. The layout needs approval.
- **A heading that does not apply to a member is left out**, never renamed or replaced. A member that needs
  a section the others lack changes the layout for the whole family, or gets a child page.
- **The parent introduces the family**: its lead names the sections every member covers, and one table
  lists every member with the values the members share.
- **Only pages of one kind are a family.** A topic beside its settings page and its errors page is not one,
  and each keeps the shape its subject needs. Reference pages take their layouts from
  [Reference pages](references/reference-pages.md).
- **The parent declares the layout** as `[family]` in its front matter, with `headings` in order and the
  infobox `labels` a member may use. `wiki check` then refuses a member that uses another heading or label, and a member
  the parent does not link; `wiki families` lists the parents whose children declare no layout.
- **The build writes the member table** when the parent names the labels to compare as `table` and puts
  `{family-table}` on its own line where the table goes: one row per member, from each member's infobox, with
  an empty cell where a member states no value.

**Read [Page families](references/page-families.md) before organizing pages, and before writing a page
into a family.** It holds how to find a family, how to design its layout, what the parent holds, and a
family done well and badly.

## Voice

- **The consequence, not the mechanism.** "An expired session does not lose your draft" — not that one
  setting outlives another.
- **Short sentences, ordinary words.** A sentence that needs reading twice is the sentence's fault.
- **One English: American, and words a person says out loud.** The gate refuses a British spelling and
  names the American word, refuses the old and legal registers -- whilst, amongst, shall, thus, thereof,
  hereby -- and refuses fellen, which is not a word. See
  [Naming and grammar](references/naming-and-grammar.md).
- **Name who acts.** "Nobody has approved it", "someone must bless it" and "anyone can run it" hide the
  fact a reader needs. Say the reader, the engineering team, an agent, or the part of the system that
  acts. The gate refuses nobody, somebody, someone, anyone, everyone and no one.
- **Say what a thing is and does.** Framing such as "the half of the tool that is not code" or "at its
  heart" names no purpose and no behavior: state what the thing is for and what it does instead.
- **No sentence without a statement.** A run-up, a transition, a summary or a restatement states nothing
  a reader can check, so it has nothing to cite — and a sentence with nothing to cite has nothing to
  say. Cut it.
- **Bold what matters**, once or twice a section. If everything is bold, nothing is.
- **A number only where a person would notice it wrong.** "About thirty seconds" beats a precise figure
  a reader cannot perceive.
- **Units a reader can feel** — seconds, meters, kilograms, days, plain counts. Convert from whatever the
  code uses; never leave that to the reader.
- **A surprising decision gets one clause of reason.** "Expiry is meant to make a stolen session useless,
  not to punish a user who went to lunch." A reader who knows why does not report it as a bug. The
  reason comes from the stated requirements or a comment in the code — never one you supply.
- **Link sideways instead of repeating**, in the prose and near the top. A thing belongs on one page, and
  every other page links to it and says so: *"Sessions live in storage, where eviction and replication are
  described; this page covers what a session is for and what it does."* Naming what a page is **not**
  about stops a reader looking for it there. Link a sibling page as `name.md`.
- **Plain present tense, no hedging.** "A session ends thirty minutes after its last request", not
  "sessions will generally tend to expire".
- **Code longer than one line is a code block**, fenced and with its language named: two commands, a
  command and its output, a settings file, a request. One name or one short command inside a sentence
  stays inline, as code.
- **Text the software shows is formatted as code**, word for word: a label, a button or a message a person
  reads on screen. The gate reads no code, so a word it refuses in prose is left alone where the interface
  itself uses it.
- **Correct grammar.** Make subjects agree with their verbs, point each pronoun at one thing, and keep
  lists parallel. The rest, and the words that say nothing, are in
  [Naming and grammar](references/naming-and-grammar.md).

## Reference pages

A **reference page** documents something a person calls or configures: a command, an endpoint, a
published function, a settings file, a form. Every rule above applies; the register changes. The names the
software owns are the content, every input has its type, default and meaning, every error is quoted
exactly, and the bar is that a reader can use the surface correctly from the page alone.

**Read [Reference pages](references/reference-pages.md) and
[Reference standard](references/reference-standard.md) before writing one.**

## Exclusions

These are not style preferences. A page carrying any of them has failed its readers.

| Never | Instead |
|---|---|
| A name only the code knows: a field, constant, function or class | The behavior it produces. A name a person uses — a command, a setting, a file they edit — is given where the page introduces the thing, and in the infobox |
| Ticks, centimetres, internal ids, requirement numbers | Seconds, meters, kilograms, plain counts |
| A task, phase, branch or ticket | Nothing; the reader cannot act on it |
| A gap list, a to-do, "not built yet" as prose | `{missing}` on the claim itself |
| An apology for what is missing | Nothing |
| A restatement of an engineering page | A link to it |
| Marketing, or persuading the reader | Description. A page that argues is in the wrong repository |
| An attribution: a rule credited to a person, with a date or a "said" | The rule itself, stated plainly. The gate refuses a dated attribution |

**Do not document absence in prose.** A reader who finds no mention of something has learned what they
needed. A section headed "not built yet" turns the wiki into a backlog, and backlogs go unread and
rot fastest.

**A planned change is one short, marked note at the end**, never mixed into the description. A reader must
never wonder whether a sentence describes today or next month.

## Citations

A citation is a numbered mark at the claim, with its reference at the foot. Write it as a markdown
footnote; the generator does the numbering.

```markdown
A session ends thirty minutes after its last request.[^expiry]

[^expiry]: `src/session/expiry.py` — `sweep()` ends a session thirty minutes after its last request,
    and holds its draft for a day afterwards.
```

- **A reference names code**: the file and function where the thing happens — not a requirements page, a
  concepts page or another wiki page. **The gate refuses a reference to
  a markdown document, or to a PDF the wiki keeps**: a document is another claim that can be wrong exactly
  as yours is, and citing it turns one error into two.
- **How an outside service behaves is cited to its own documentation** — a host's settings, a platform's
  defaults: the thing the project does not run. Name the publisher, link the page by its title, and say
  what it states. A `{missing}` on such a claim means that documentation has not been checked yet.
- **A reference marks the code; it never links to it.** Outside documentation is the only linked reference. Write `` `src/session/expiry.py` — `sweep()` ``,
  not a markdown link. A link to a source file works only while the site is served from inside the
  repository, and is dead wherever the site is published.
- **Configuration counts as code** where a number lives there: name the function that reads it *and* the
  row.
- **References are the only place a path belongs**, and a user build strips them.
- **Link other pages, pictures and PDFs relative to your own file**, so the link works in the markdown and in
  the browser. A link to a page the wiki does not have is drawn red, and the gate refuses it: write the
  page, or link to one that exists.

## Citation coverage

**Every sentence is a statement, and carries its own reference.** A sentence states a fact, a behavior,
a rule or a consequence; one that states none of those adds nothing to the page, and is cut. So every
sentence ends with a citation or `{missing}` — every one, not the surprising ones, and never on the
strength of its neighbor's.

**The gate refuses a sentence that cites nothing.** A citation after the full stop belongs to its
sentence. A sentence that links to another page is excused, because that page carries the citations.
**Every table row cites in at least one of its cells**, or carries `{missing}`; the header row is exempt, and
one cited row never covers the rows beside it. A list item that is a bare link — the host's own guides, under **External
links** at the end of a page — states nothing and is excused too. Write an outside link as a plain link; the build
opens it in a new tab, marks it `nofollow` and adds the arrow. Only a page about the wiki itself is exempt, because it describes no
behavior.

A reader uses the wiki **instead of** the source, so a sentence they cannot trace must be taken on faith —
and it looks exactly like one that was checked. **"No source" is a fine answer; silence is not.**

Every build and check prints how many sources each page cites and how many claims it marks as having
none, with totals. `wiki check` names every failing sentence and every marked claim by page and line;
read both before calling a page done.

## Missing citations

Write `{missing}` after the claim, or `missing = true` on an infobox row. A red mark renders where the
citation would be.

It means **nothing was cited**: either the system does not do this yet, or the writer has not found where it does.
To a reader both mean the same — do not take this on faith — so one mark serves both. A user never sees
it.

It is the only sanctioned way to say a thing is not built. Use it where a reader would otherwise assume
the thing exists.

**A requirement stated before it is built is written now, and marked.** The wiki can lead the code: a
stated requirement may describe a feature, a change or a whole idea, so its documentation takes shape
before the code is built. Each statement of it goes on the page it belongs to, carrying `{missing}` because
nothing implements it yet. A page written that way, or a whole wiki, can be mostly red marks, and that is
correct: it is the idea, stated plainly, waiting for its code.

- **Only the stated requirements.** A requirement never stated is invented, however likely it seems; it is not
  written, marked or not.
- **Write it as the behavior it asks for**, in the present tense and with the same rules as any other
  sentence, so the page reads the same once it is built and only its marks change.
- **The mark comes off with a citation** to the code that does the thing, in the change that builds it.
- **A change to something already built** is one short, marked note at the end of its page, never mixed
  into the description of what it does today; a thing not built at all is written as its own page.
- **A command or endpoint that does not exist yet** is written as its contract, as
  [Reference pages](references/reference-pages.md) describes.

## Infobox

The infobox is the page's reference card: the thing's names, the values that govern it and the rules it
keeps. It summarizes the page, and **never states a fact the page does not.**

- **Groups, in order**: Identity, the names a person types or searches for; Values, the figures that
  govern it, in units a reader can feel; Rules, what it refuses, always does or never does.
- **A label is a noun phrase and its value completes it**: "Expiry · 30 minutes". The gate refuses a value
  that is only yes, configurable, varies or depends.
- **Every row cites** a footnote the prose cites for the same fact, or carries `missing = true`. The gate
  refuses a row with neither, or one citing a footnote no sentence uses.
- **Two to eight rows.** More is the prose again, as a table.

**Read [Infobox](references/infobox.md) before writing or changing one.** It holds each group, label and
value, the keys a row takes, and an example.

## Diagrams

A flow, a sequence or a state machine is drawn as a diagram, written as a `mermaid` code block, the way
GitHub draws one. The site draws it with no network, and the page's markdown keeps it as written.

**Read [Flowcharts](references/flowcharts.md) before drawing one.** It holds when a diagram earns its
place, which kind to draw, its shapes, direction and labels, and a draft beside the finished drawing.

- **A diagram states behavior**, so the sentence introducing it carries the citation, and every box and
  arrow is something the cited code does. Never draw a step the code does not have.
- **Name its parts as the page does**: the same words for the same things.
- **One question per diagram**, answered in about ten steps at most.

## Charts

Figures are drawn in the same `mermaid` block, whose first word names a kind of chart instead of a
diagram: bars and lines over an ordered run, a pie of the parts of one whole, a flow of quantities, a
quadrant or a radar. A diagram draws how something works; a chart draws how much.

**Read [Charts](references/charts.md) before drawing one.** It holds when a chart beats a table, which
kind to draw, where its numbers come from, how it is labeled, and a chart done well and badly.

- **A chart draws figures the page already states and cites.** It is never the only place a number
  appears: a drawing cannot be searched, read aloud or copied, and the sentence introducing it carries the
  citation.
- **A table until the shape is the point.** Four numbers a reader compares one by one are a table; a rise
  across twelve months is a chart.
- **Never draw a figure that moves faster than the page.** A count that is different next week is stale
  the day after it is drawn, and nothing on the page says so.

## Pictures

A page shows the thing it describes. Put pictures in `docs/wiki/images/`, reference them by a relative
path, and caption every one; a caption is prose and obeys every rule here.

Each picture has an entry in `PICTURES.toml` naming what it depicts. **When a depicted file changes and
the picture has not been redrawn, the gate fails.** Redraw it, or run
`wiki bless <picture> "<why it is still true>"` when the change left the picture true. The reason is the
record that the picture was looked at.

## PDFs

A page can hand the reader a document the project keeps, such as a policy, as a PDF. Put it in
`<wiki>/files/`, beside `images/`, and link it with an ordinary markdown link relative to your page:
`[Refund policy](../files/refund-policy.pdf)`. The site writes its size after the link and, on a computer,
opens it over the page.

- **Only a PDF directly in `files/` is published.** The gate refuses a link to a PDF anywhere else, a link to
  one that does not exist, and a PDF over 20 MB.
- **A PDF is not a citation.** A sentence that links one still carries its own reference to the code, and a
  reference that links one is refused.
- **Name the document in the link text**: the reader sees it before the size, and as the title of the PDF
  when it opens.

## Truthfulness

The page describes **what the thing actually does**, and nothing else — except what the stated requirements
ask it to do and nothing does yet, which is written and marked `{missing}`, as
[Missing citations](#missing-citations) describes.

**Never invent.** Everything on a page comes from one of three places: **the code**, **the stated
requirements**, or **an outside service's own documentation** for how that service behaves. Nothing else is a
source — not what is typical, what similar tools do, what seems likely, what would make the page
complete, or what you would have built.

- **No invented behavior**: no feature, option, default, limit, error, step or edge case the code does
  not have.
- **No invented reasons**: a why comes from the stated requirements, or from a comment or commit in the
  code, never from a plausible guess about what the code's author intended.
- **No invented requirements, plans or audiences**: only what the stated requirements say.
- **No invented examples**: every sample, output and message is copied from a real run or from the code.
- **No invented names**: a thing is called what the code or the stated requirements call it.
- **A gap stays a gap.** Where the page needs a fact no source gives, mark the claim `{missing}` or leave
  it out, and ask for the requirement. A sentence you cannot trace to one of the three sources is deleted, not
  softened into a hedge.

1. **Read the code for every claim** — not the configuration, another document, or what a task said would
   be built.
2. **Say what is uncertain.** Where behavior is emergent, untested or could not be determined, say so
   plainly. **A confident sentence covering a gap is the worst thing a page can hold**, because the reader
   is using it *instead of* the code and cannot catch it.
3. **Never guess a number.** Without one, describe the behavior.
4. **When the page and the thing disagree, the page is wrong.** Fix it. A page is never grounds for calling
   the implementation wrong; only an approved requirement says what it ought to do.

## Coverage

**Behavior no page mentions is as wrong as a page the code contradicts.** A reader using the wiki instead
of the source never learns it exists, and nothing on any page warns them. **Coverage means behavior and
requirements**: what a person meets when they use the system, and what the stated requirements say it
must do. A task covers the part of the code it touches; an inventory of the whole code is a review, run
when a task asks for one.

- **Inventory from the code, never from the wiki**, so the wiki cannot hide its own gaps. List the
  behavior a person meets: commands and options; endpoints, public functions, events; data a person sees
  or changes; refusals, error messages, exit and status codes, limits; jobs, workflows, builds,
  deployments; outside services; roles and permissions. Then add every stated requirement.
- **A setting is a sentence, not a page.** It goes on the page whose behavior it changes, and only when it
  changes something a person or an outside service notices. Plumbing a reader never meets, such as a
  connection pool or a log format, is left out. A settings file gets its own page only when the project
  defines it and a person edits it.
- **Every item has a home**: a page, or a section of one. An item only mentioned in passing, without its
  behavior, is not covered.
- **Walk it the other way too.** A source file whose behavior a person meets, and that no reference cites,
  is usually an undocumented feature. `wiki coverage` lists every such file, and every citation of a file
  that no longer exists, once `wiki.toml` has a `[coverage]` table naming the source files.
- **A new behavior gets its page in the same change as its code.** Leave out internals a reader never
  meets, such as private helpers and test code.

## Reading budget

A page must answer in about two minutes, and the goals page must read in one sitting. The gate enforces a
word count as the proxy, and prints every page's count on every build. References and code blocks are not
counted: one is followed and the other copied, so neither is read the way prose is.

The count is a backstop; **the intent is the control.** A page inside its budget that carries a sentence
serving nothing is still wrong, and a page over it is saying its intent has grown.

## Approval

- **Changing an intent needs approval**, recorded with the work and never on the page, because
  it changes what the thing is for.
- **Changing detail below an intent does not.** A retuned number that alters no outcome is recorded, not
  approved.
- **If a change cannot be made without altering an intent, stop and ask.** It is a design decision, and it
  is not yours to make.

## Definition of done

1. The intent is two to four sentences saying what the thing is for, not how it works.
2. Every sentence serves the intent.
3. The prose holds no name only the code knows, no unit a reader cannot feel, and no task or gap list.
4. Every sentence states something read from the code and carries its own citation, or `{missing}`;
   every uncertain claim says so.
5. Mechanism links out instead of being retold, a subject of its own is a child page, and a page in a
   family follows the family's layout.
6. The infobox gives the thing's names, values and rules under noun labels, and every row cites a
   footnote the prose cites, or is marked missing.
7. `wiki check` passes.
8. A reader who has never read the source can follow the whole page, and each reader in
   [Readers](#readers) finds, in the parts of the page that table names for them, the facts it says they
   come for.
9. The behavior the change touched, and every requirement stated for it, has a page or a section.
10. Nothing on the page was invented: every statement traces to the code, the stated requirements, or an
    outside service's own documentation.
