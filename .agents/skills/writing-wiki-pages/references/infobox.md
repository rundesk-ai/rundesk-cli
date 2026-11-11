# Infobox

Read this before writing or changing an infobox. `SKILL.md` holds the summary; this holds each group,
the label and value a row pairs, the keys a row takes, and an example.

The infobox is the page's reference card: a reader glances at it for the thing's name, the values that
govern it and the rules it keeps. It summarizes the page, and **never states a fact the page does not.**

## Contents

Rows come in three groups, in this order:

| Group | Holds | Rows, for a page about sessions |
|---|---|---|
| **Identity** | The names a person uses to find, run or change the thing, exactly as they type or search for them | Cookie · session_id; Setting · session.timeout |
| **Values** | The figures that govern it — limits, defaults, durations, counts — in units a reader can feel | Expiry · 30 minutes; Size limit · 4 kB |
| **Rules** | Its core logic, each in a phrase: what it refuses, what always happens, what never does | Overflow · refused, never truncated; Signing out · this device only |

- **A named thing opens with its name.** A page about a command, a skill, a setting or a service starts
  with a **Name** row giving the name exactly, so a reader who knows it recognizes the page.
- **Identity holds the names a person uses**: what they type, search for, open or configure. Never a
  function, class or internal id; those belong in the references.
- **A group is named for what it holds**: Identity, Values and Rules, or something more precise when every
  row shares it — **Limits**, **Defaults**, **Exit codes**, **Contents**. Never "Info", which names nothing.
- **Leave out** what a reader never looks up: every setting there is, a value that needs a sentence, a fact the
  thing does not do.
- **Every row cites.** A row carries `cite = "<footnote>"`, naming a footnote the page's prose cites for
  the same fact, and renders with that citation's number. A row with nothing to cite carries
  `missing = true`. **The gate refuses a row with neither, or one citing a footnote no sentence uses**: a
  row is a claim in the most visible place on the page.
- **Two to eight rows.** More is the prose again, as a table.

## Labels and values

A label names a property and its value gives it, so the pair reads as a statement: "Expiry · 30 minutes"
is *the expiry is thirty minutes*.

- **A label is a noun phrase in sentence case**: **Name**, **Expiry**, **Size limit**, **Default port**.
  Never a verb ("Expires"), a question ("How long it lasts") or a clause. Singular for one value, plural
  for a list: **Command** · wiki sync; **Commands** · wiki build, wiki publish.
- **A value is a name, a figure or a short phrase**, with no full stop: a name exactly as typed; a figure
  with its unit, such as 30 minutes or 4 kB; a rule as a phrase, such as "refused, never truncated"; a list
  separated by commas. A value that needs a subject and a verb belongs in the prose.
- **Never a hedge or a yes.** "Configurable", "varies" and "yes" give a reader nothing to check. Give the
  default or the condition, or drop the row. The gate refuses a value that is only yes, configurable,
  varies or depends.
- **One property, one label, on every page.** If one page says **Command**, no page says "Run with".
- **A `note`** is the single clause that stops a value being misread, such as "after the last request".
  Never a second value.
- **`link = "https://…"`** links the value to an address outside the wiki, such as an author's site. A
  page is linked from the text, never from a row.
- **`missing = true`** renders the red mark beside a value nothing implements, or whose implementation has not been found.
- **`guaranteed = "<requirement id>"`** records the requirement a row satisfies, for whoever next checks
  the page against the code. It is never rendered.

## Example

```toml
[[infobox]]
group = "Identity"
rows = [
  { label = "Cookie", value = "session_id", cite = "cookie" },
  { label = "Setting", value = "session.timeout", cite = "timeout" },
]

[[infobox]]
group = "Limits"
rows = [
  { label = "Expiry", value = "30 minutes", note = "after the last request", cite = "expiry" },
  { label = "Size limit", value = "4 kB", cite = "size" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Overflow", value = "refused, never truncated", cite = "size" },
  { label = "Signing out", value = "this device only", cite = "signout" },
]
```

[Page standard](page-standard.md) sets this infobox beside one that fails, and says why.
