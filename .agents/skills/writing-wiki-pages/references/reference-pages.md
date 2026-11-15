# Reference pages

Read this before writing a page for something a person calls or configures: a command, an HTTP
endpoint, a function a project publishes, an event, a settings file, or a form. [Reference
standard](reference-standard.md) shows a command page and an endpoint page done well and done badly,
and [Naming and grammar](naming-and-grammar.md) holds the rules for the names these pages are made of.

A reference page is still a page. It has an intent, cites every claim, names its headings with nouns,
and passes `wiki check`. What changes is the reader and the register.

## Reader

The reader is about to call the thing. They arrive knowing what they want done and look up exactly how.
**The bar: the reader can use the surface correctly from the page alone**, without reading the code or
asking the people who built it — and when a call fails, can tell from the page why, and what to do.

- **Dense and factual.** A table for parallel facts; prose for behavior a table cannot hold.
- **The names the software owns are the content.** Write them exactly, as code.
- **Only the published surface.** The function or class that implements it belongs in the references,
  never in the page.
- **One page per command or endpoint**, or per small group, nested under an index page that lists every
  one on a line. Completeness is then checkable by counting.
- **Explanation lives on its topic page.** The lead links there, saying what that page covers; the topic
  page links back to the reference.

## Page shapes

Sections in this order. Leave out a section that does not apply; never write an empty one.

### Command

| Section | Holds |
|---|---|
| Usage | the command line exactly as its help prints it, then one real call |
| Options | Option · Meaning · Default |
| Arguments | Argument · Meaning, with whether each is required |
| Output | what it prints, on standard output or standard error, and what it changes on disk |
| Exit codes | every code, the condition that produces it, and its message where it has one |

### HTTP endpoint

| Section | Holds |
|---|---|
| Request | the method and path exactly, then one real request |
| Authentication | what the request must carry, and what a missing or wrong credential returns |
| Parameters | Name · In (path, query or header) · Type · Required · Meaning |
| Body | Field · Type · Required · Meaning, with units, limits, and what absent and null each mean |
| Responses | Status · When · Body |
| Errors | Status · Code · Condition · Message |
| Limits | rate, size, timeout, pagination, and whether a repeated call is safe |
| Example | one real response, and one real failure |

### Published function

| Section | Holds |
|---|---|
| Signature | exactly as a caller imports and calls it |
| Parameters | Parameter · Type · Required · Default · Meaning |
| Returns | what comes back, and in which cases |
| Errors | what it raises, the condition, and the message |
| Example | one real call and its result |

### Settings file

Only for a file the project defines and a person edits. A setting of another kind is a sentence on the
page whose behavior it changes.

| Section | Holds |
|---|---|
| Location | where the file lives, and its format |
| Keys | Key · Type · Default · Meaning |
| Validation | each value that is refused, and the exact message |

### Event

| Section | Holds |
|---|---|
| Name | exactly as a consumer subscribes to it |
| Trigger | what has happened when it is sent |
| Payload | Field · Type · Meaning |
| Delivery | ordering, repeats and retention, only as far as the code establishes them |

### Form

A form, or a flow of questions. Every question, answer and message is copied from the interface, word for
word, in code formatting.

| Section | Holds |
|---|---|
| Flow | one diagram of the question groups in order, then one diagram per group for its branches, so each stays within about ten steps |
| Groups | a table per question group: # · Question · Answers · Required · Shown when · Field |

## Contract

- **Every input answers four questions**: its type, whether it is required, its default, and what it
  does. A blank cell is a gap; where the answer could not be found, write `{missing}` in the cell.
- **Conditions are stated as conditions.** "Required when `mode` is `replace`", never "sometimes
  required".
- **Units and limits are figures**: "1 to 8", "in seconds", "at most 60 a minute".
- **Absent, null, zero and empty are four different facts.** Say which a field accepts and what each
  means.
- **Every error is quoted exactly**: its status or exit code, its error code if it has one, the condition
  that causes it, and the message word for word. Errors are the half of a contract an integrator needs
  most and the half most pages leave out — a caller can guess the success from one call, and cannot guess
  the failures without meeting them.
- **What is refused is documented where a reader would try it**: an unknown field, two options that
  cannot be given together.
- **Side effects are stated**: what the call writes, sends or deletes, and whether calling it twice is
  safe — only as far as the code establishes it.
- **Say what a caller cannot guess, and nothing they can.** "`id` — the id" is not a meaning.
- **A deprecated input is marked in its row**, with its replacement. History belongs in the release notes,
  not in the prose.

## Examples

- **One example that works, copied from a real run**, with the output it produced. A template such as
  `[options] <name>` under a heading called Example teaches nothing.
- **Placeholders are capitals** in usage lines (`OUT`, `PICTURE`); examples use real values.
- **Show one failure** beside the success: the smallest wrong call and its exact error.
- **Only stable output.** Leave out timestamps, generated ids and machine-specific paths, or say beside
  the sample that they will differ.
- **A fragment says it is one**, beside it, not in a note further down.
- **A code sample needs no citation**, and is not read as prose by the checks. The sentence that
  introduces it does need one.

## Accuracy

- **Copy the structure from the source of truth** — the help output, the route definition, the schema,
  the signature — and cite where it is defined. Never retype an option list from memory.
- **Run it before writing it.** Produce every example and every quoted error, then paste what was
  produced.
- **When the definition changes, the page changes in the same commit.** A wrong reference is worse than
  none, because it is followed.
- **The page is written, not generated.** A page produced from the definition agrees with it whatever it
  does, so it can never show the code disagreeing with what was intended. Copy from the definition; do
  not derive the page from it.
- **Where the code and an older description disagree**, the page describes the code, and the
  disagreement is raised for approval. Never average the two into a hedge.

## Unbuilt surfaces

When a stated requirement specifies a command or an endpoint that does not exist yet, write its page as
the contract, with every row that nothing implements marked `{missing}`.

- **One condition to a row**: in this situation, this caller can or cannot do this, producing this
  result.
- **No implementation names** in a requirement. They describe a design, and they are wrong after the next
  refactor while still reading as true.
- **No word whose meaning would change what gets built**: appropriate, seamless, as needed, normal, etc.,
  and/or.
- **A row holding two conditions is two rows.**
- **The change that implements a row replaces its mark** with the citation of the code that does it.

## Definition of done

1. Every command, endpoint, option, field and error the surface has is on a page, and nothing it does
   not have.
2. Every input has its type, whether it is required, its default and its meaning.
3. Every error is quoted exactly, with its condition.
4. Every example was run, and shows what the run produced.
5. Every name matches its source, character for character.
6. A reader who has never seen the code could make a correct call, recognize a failed one, and know why it
   failed.
