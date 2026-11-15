# Naming and grammar

Read this before naming a page, a heading or a label, before describing a name the software already has, and
before the final pass over any page. `SKILL.md` holds the method — ask the question, name the answer —
and the five tests for a name. This holds the rules for each kind of name, how to write about the names
the software owns, and the grammar every page is held to.

## Kinds of name

A page carries names **you choose** and names **the software owns**. They follow opposite rules, and
most naming mistakes are one kind treated as the other.

| | Names you choose | Names the software owns |
|---|---|---|
| Examples | page titles, headings, categories, infobox labels, table columns, captions | commands, options, fields, settings keys, endpoints, error codes, file names |
| Rule | a noun phrase a reader would say, in plain words | exactly as the software spells it, every time |
| When the name is poor | rename it | document it as it is, and report it as a finding |

**A page is not a rename.** When a setting is called `retry_mode_flag`, the page says `retry_mode_flag`,
however much clearer "retry limit" would be. A reader who searches the code, the help or the error log
for your better word finds nothing. Say what the value means beside the name, and raise the poor name as
a finding rather than fixing it in prose.

## Names you choose

### Page titles

The thing the page is about, as a reader would say it: **Refunds**, **Session expiry**, **Nightly run**.

- **A noun phrase**, never a task ("Managing refunds") or a question ("How refunds work").
- **No leading article.** **Site**, not "The site". Keep one only when it is part of what people call the
  thing.
- **Singular for one thing, plural for a set**: **Session expiry**, **Refunds**.
- **A page about a named thing a person types is titled with that name**, exactly: a page about the
  `export` command is titled `notes export`, not "Exporting notes".

### Subtitles

A short description under the title, naming the specific things the page covers: **word limits for a
page, an intent and the goals page**.

- **Things, not a clause about them.** "what a build makes" and "how a page sits on the screen" are the
  writer's question; name the answer: **the built pages, their addresses, dates, search and audiences**.
- **No vague word stands in for a thing**: not "and other drawings", "something", "here" or "this
  machine".
- **No slogan or contrast.** "labels, not questions" rates the page instead of describing it.
- **Lower case, no full stop**, and on a reference page the software's own help line, exactly.

### Headings

A label on a drawer: **Expiry**, **Size**, **Signing out**. `SKILL.md` has the method; these are the
grammar.

- **Sentence case**, no full stop: **Reading budgets**, not "Reading Budgets."
- **One subject.** A heading joined with "and" is usually two sections.
- **No numbers or counts** ("Three limits"). The count changes; the subject does not.
- **No demonstratives.** "This site", "Our setup" and "These options" point at the page they sit on
  instead of naming a subject, and read as nothing in a contents box or a search result: **Example**,
  **Setup**, **Options**.
- **A gerund is a noun and is fine** (**Spreading**). A gerund phrase is usually the question in
  disguise ("Getting started" wants to be **Setup**).
- **On a reference page, name the part of the contract**: **Usage**, **Options**, **Errors**, **Exit
  codes**. A reader scans for those words.

### Categories

A plural noun for a set, sentence case: **Commands**, **Refusals**, **Wild animals** — never "Animals that
are wild".

### Infobox labels and table columns

A noun phrase naming a property; the value or the cell gives it.

| Instead of | Write |
|---|---|
| A column headed "Is it retried?" | **Retried** |
| A label "Why it was archived" | **Reason** |
| A label "Expires" with the value "yes" | **Expiry** · 30 minutes |
| A label carrying its own explanation | The noun, with the explanation in a `note` or the cell |
| A label "This site", with the site's address as its value | **Domain** |

Put a unit in the label only when every value shares it: **Timeout (seconds)**. Otherwise the unit goes
with each value.

### States

Adjectives or past participles, never verbs: **Draft**, **Approved**, **Archived** — not "Approve" or
"Currently active".

## Names the software owns

### Code formatting

In prose and tables, a name the software owns is formatted as code — `retry_limit`, `--port`,
`POST /invoices` — so a reader can tell a name from an ordinary word, and copy it. Keep its case and
punctuation even at the start of a sentence; better, rewrite the sentence so it does not start with one.
Infobox values render as plain text, so write them there exactly as typed and without backticks.

Text the software shows a person is formatted the same way, word for word: a label, a button, a message.
The gate reads no code, so a word it refuses in prose is left alone where the interface uses it.

Anything longer than one line — two commands, a command and its output, a settings file, a request — is a
fenced code block with its language named, never a run of inline code one line at a time.

### Terms

Before drafting, list the terms the page will use and where the software defines each. Then hold the
list for the whole page:

```text
Term        Defined in                     Never write instead
attempts    retry(fn, attempts=...)        tries, retries, the count
backoff     retry(fn, backoff=...)         delay, wait, sleep interval
archived    the invoice status value       closed, inactive, removed
```

A synonym reads as a distinction. The reader who meets "tries" beside `attempts` goes looking for the
difference, and there is none. Define a term once, where it first appears, and never redefine it.

### Verbs

| Meaning | Use | Do not mix in |
|---|---|---|
| An error leaves the thing | raises, or refuses | throws, emits, errors out |
| An error passes through unhandled | propagates | bubbles up, escapes |
| The thing is run | runs, or calls | invokes, triggers, fires, executes |
| A value comes back | returns | gives back, yields, produces |
| Something is stored | writes, or records | saves, persists, puts, dumps |

Choose the verb the software's own messages use, and keep it.

### Field descriptions

What value it holds, its unit or format, its limits, its default, and what absent means.

```text
Bad:  `timeout` — The timeout.
Good: `timeout_seconds` — how long a request waits for a reply, in seconds, from 1 to 300; defaults to
      30. Absent means the default, not "wait forever".
```

Say only what the code establishes. Leave out a limit the code does not enforce rather than guessing one, and mark
a required fact the writer could not find with `{missing}`.

### Messages and codes

An error message, an exit code, an error code and a log line are quoted word for word, as code. A reader
searches the page for the message they were shown, and a paraphrase is a miss.

### Poor names

The page documents the name that exists. A writer who can see a poor one reports it as a finding, because a
name that misleads the writer will mislead every reader.

| Sign | Example | What it costs |
|---|---|---|
| The type in the name | `name_str`, `count_int` | the type is in the schema, and it changes |
| A question or a sentence | `did_the_user_confirm` | the value is unnamed; it wants `is_confirmed` |
| A negative boolean | `is_not_active`, `disable_email` | a double negative at every use |
| A number with no unit | `timeout`, `size`, `price` | the unit is guessed, most expensively for money |
| A generic noun | `data`, `info`, `details`, `meta` | what it holds was never decided |
| A numbered suffix | `notes2`, `extra_field` | a second meaning left unnamed |
| An abbreviation outside the domain | `qty_rcv`, `dt_crt` | comprehension paid on every read |
| A plural holding one value | `invoice_ids` holding one id | promises a collection |
| The mechanism, not the value | `retry_mode_flag` | the value itself has no name |
| A verb for a state | a status of `archive` | a state is a past participle: `archived` |
| The row operation for a business event | `created_at` meaning "received" | two different facts in one name |
| Mixed conventions | `createdAt` beside `updated_at` | two parsers for one surface |

### Naming conventions

A project's own convention wins over every line of this table. Where it has none, these are the forms a
reader expects:

| Kind | Form | Example |
|---|---|---|
| Boolean | `is_`, `has_` or `can_`, stated positively | `is_active`, `email_enabled` |
| Instant | the event, then `_at` | `archived_at` |
| Date | the event, then `_on` | `effective_on` |
| Reference to another record | the entity, then `_id` | `invoice_id`, `approved_by_id` |
| Quantity | the unit as a suffix | `timeout_seconds`, `size_bytes` |
| Money | minor units, with the currency beside it | `amount_cents` and `currency_code` |
| Stored state | an adjective or past participle | `draft`, `archived` |
| Event | the entity, then what happened, past tense | `invoice.paid` |
| Error code | the entity, then the condition | `INVOICE_NUMBER_TAKEN` |
| Command option | lowercase words joined by hyphens | `--skill-dir`, `--no-skill` |

## Grammar

A page is read instead of the code, so a sentence that can be read two ways is a fact that can be read
two ways. These rules settle most cases.

### Sentences

- **Name the actor.** "`wiki check` refuses the page", not "the page is refused". The actor is usually the
  fact the reader came for. Passive voice is right only when the actor genuinely does not matter.
- **Present tense for what exists.** No "will", "currently", "new" or "now" in a claim about behavior.
  A planned change is one marked note at the end of the page. The gate refuses "currently", "at the
  moment" and "for now".
- **Subject and verb agree**, across whatever sits between them: "the goals page collects", "a list of
  pages is", "neither option is".
- **The fact first.** Lead with the result, then the condition: "A draft is refused when a reader cannot reach
  it", not "When a reader cannot reach it, a draft is refused."
- **One idea per sentence.** A sentence that needs reading twice is two sentences.
- **A pronoun points at one thing.** When "it" or "this" could mean either of two nouns, name the noun.
- **Name the nearest actor; never point at the project.** "This repository", "this wiki", "this tool" and
  "our site" mean nothing to a reader who arrived from a search or a link. Name the part of the system
  that acts, such as the results page or the server, and write the project's name only where no nearer
  part acts. The gate refuses them outside code, where a message the software prints is quoted as it is.
- **No fragments in prose.** A fragment is right in a table cell, an infobox value or a caption, and wrong
  in a paragraph.
- **Parallel lists.** Every item in a list starts with the same part of speech and has the same shape.

### Numbers and units

- **Figures for every value a reader compares, types or checks**: 500 words, port 8787, exit code 2.
- **Words for a round, approximate quantity in a sentence**: about thirty seconds. Hold one choice for
  one quantity across the page.
- **A space between a number and its unit**, and the unit a reader would use: 4 kB, 30 minutes.
- **Ranges say both ends**: 1 to 8, not "up to 8" when the floor matters.

### Punctuation

- **No exclamation marks.** A page describes; it does not cheer.
- **Code formatting or quotation marks, never both.** Code formatting for what the software owns;
  quotation marks for a word used as a word, or a sentence quoted from a person.
- **A dash sets off an aside.** If the sentence works without the aside, cut the aside. At most one pair
  in a paragraph.
- **A colon promises what follows.** What comes after it completes what came before.
- **The serial comma is a house choice.** Pick one for the wiki and hold it.
- **No terminal punctuation** on titles, headings, labels, columns or a caption that is a phrase. A
  caption that is a full sentence ends with a full stop.

### Capitalization

- **Sentence case** for titles, headings, labels, categories and columns.
- **A name keeps its own case**: a product name as its makers write it, a name the software owns
  exactly as it is spelled.

### Spelling

**American English, and words a person says out loud.** The gate refuses a British spelling and names the
American word to write: behaviour, colour, licence, labelled, centre, judgement, grey, towards, analyse,
and every verb spelled -ise where American English spells it -ize. It refuses the old register and the
register of contracts the same way: whilst, amongst, shall, ought, thus, hence, notwithstanding, albeit,
thereof, therein, aforementioned, hereby, herein. It refuses fellen, which is not a word. A name the
software owns is written the way the software spells it, and code is never read.

### Words that say nothing

Each of these survives a first draft and carries no fact.

| Pattern | Examples | Instead |
|---|---|---|
| Hedges | appears to, should generally, may, typically, in some cases | state what the code does, or mark it `{missing}`. The gate refuses all but may |
| Minimizers | simply, just, easily, of course, obviously | delete the word. The gate refuses all but just |
| Marketing | powerful, seamless, robust, cutting-edge, best-in-class | delete the clause. The gate refuses them |
| Preamble | note that, it is worth noting, please be aware, in order to | keep the fact, drop the frame. The gate refuses them |
| Empty amounts | a number of, reasonable | the number, or the condition. The gate refuses them |
| Stacked connectives | moreover, furthermore, additionally | say the actual relationship, or nothing |
| Contrast by denial | it is not just X, it is Y | say Y |
| Vague verbs | handle, manage, deal with, process, support | the verb that happens: refuses, writes, retries |
| Intentions for machines | the check wants, the server tries to | what it does, and under what condition |
| Open lists | etc., and so on, various, and/or | the whole list, or the single thing. The gate refuses them |
| Vague references | the one, the ones, anything | the thing itself: the tag, the section, the error. The gate refuses them |
| Hidden actors | kept, is kept, are kept | who keeps it, or where it lives: the build writes it, the files folder holds it. The gate refuses kept |
| Question clauses | what a person writes, how it works, where it lives | the thing itself: page files and their intent. The gate refuses them in headings and subtitles |
| Pointing elsewhere | see the documentation for details | link the exact page, or state the fact |
| Vague actors | nobody, somebody, someone, anyone, everyone, no one | name who acts: the reader, the engineering team, an agent, the build. The gate refuses them |
| Empty framing | "the half of the tool that is not code", "at its heart", "the other side of" | say what the thing is and what it does |

## Last pass

After the content is right, read the page once for language alone:

1. **Read it aloud.** Anything no person would say gets rewritten.
2. **Check every name the software owns** against its source, character for character.
3. **Check the term list** — one word per concept, one verb per meaning.
4. **Search for the words that say nothing**, and remove each one you find.
5. **Read the titles, headings and labels alone.** Each is a noun phrase in sentence case with no
   punctuation.
