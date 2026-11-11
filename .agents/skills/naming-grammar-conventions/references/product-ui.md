# Write product interface language

Dos and don'ts for every string a person reads on screen. Read `data-and-contracts.md` alongside this whenever a label corresponds to a stored or published field.

**Every string occupies a slot. Each slot has one job and one grammatical form.** Almost all bad interface copy is a right sentence in the wrong slot: an explanation stuffed into a label, a story stuffed into an empty state, a feature description stuffed into a column header. The fix is rarely to rewrite the string. It is to split it and move the pieces to the slots that want them.

## 1. Shared mechanics

Use these as defaults when the product has no documented content style. Regulated wording, localization, platform conventions, and the established design system take precedence.

### Capitalization
**Prefer sentence case for English product interfaces.** Apply the chosen convention consistently to labels, headers, buttons, titles, menu items, tabs, and options.

- `Retry limit`, not `Retry Limit`
- `Add line item`, not `Add Line Item`
- Capitalize only the first word, proper nouns, product names, and defined system terms that are capitalized in the lexicon.

Do not introduce title case beside an established sentence-case interface. If the product uses title case, document its capitalization rules rather than deciding word by word.

### Punctuation
| Slot | Terminal punctuation |
|---|---|
| Labels, headers, buttons, titles, tabs, menu items | None |
| Tooltips, help text, descriptions | Period, even for one sentence |
| Errors, empty states, confirmations, toasts | Period |
| Placeholders | None |

Use punctuation appropriate to the slot and the product style. Labels and controls usually omit terminal punctuation; sentences, questions, regulated wording, and localized strings follow their grammar.

### Em dashes
Prefer direct sentences over routine em-dash asides in operator interfaces. Preserve an established editorial style when it is deliberate. Use `—` as a null marker only when the product has adopted it consistently and accessibility and localization checks support it.

### Numbers, dates, units
- Follow the product's number style. Digits are a strong default for operational values and compact interface text.
- State the unit next to the value or in the label: `Timeout (seconds)`, `Size (MB)`.
- Use absolute timestamps where precision matters. Relative time can suit live activity when the exact value remains available.
- Show the timezone whenever readers could otherwise interpret an instant differently.
- Currency with an explicit code where more than one is possible: `1,250.00 USD`.
- Percentages, ratios, and rates get their basis stated: `Completion rate (jobs to completions)`.

### Abbreviations and acronyms
Expand unfamiliar abbreviations on first use when space and context allow, then abbreviate:
`application programming interface (API)`. Preserve widely recognized domain abbreviations. Do not
invent one merely to shorten a label.

### Interpolation and pluralization
- Never concatenate sentence fragments. Build whole strings with placeholders: `{count} invoices selected`, not `"" + count + " invoices selected"`.
- Handle plurals with real plural rules, never `item(s)` and never `1 items`.
- Never build a sentence whose word order assumes English grammar if the product will ever be translated.
- Give translators the whole string, its slot, the action and object it names, and enough context to
  resolve noun/verb ambiguity. Locale-specific wording may map to the canonical concept without
  matching English grammar mechanically.
- Avoid idioms, metaphors, and culturally specific references. They translate badly and add nothing.

### Accessible names
Every interactive element needs an accessible name that contains its visible label when one exists
and still distinguishes the control.

- Icon-only buttons: the accessible name is the verb plus object the icon performs. A trash icon is `Delete invoice`, not `Trash`, not `Button`.
- Decorative images and icons: empty alt, hidden from assistive tech.
- Informative images: alt text states the information, not the appearance.
- Form fields: a real `<label>` bound to the input. A placeholder is never an accessible name.
- Status changes announced to screen readers use the same string as the visible message.

### Truncation
Truncate at the end, never the middle, unless the tail is the distinguishing part (file paths, IDs). Any truncated value shows the full value on hover and in the accessible name. Never truncate a label; shorten the label instead.

---

## 2. Navigation and structure

### Page title
**Form:** lexicon noun, plural for collections, the record's name for detail pages. One to three words. No verbs, no articles, no possessives.

| Good | Bad |
|---|---|
| Archived records | Manage your archive list |
| Invoices | Invoice management |
| Workspace alpha | Invoice detail view |

The definition of the concept does not go here. It goes in the page tooltip.

### Navigation item
**Form:** identical string to the destination page title. Never a variant, never a verb.

### Tab
**Form:** noun naming the subset, not the act of viewing it. `Active`, `Archived`, `All`. Not `View archived`. Tabs within a group are grammatically parallel.

Tabs partition one collection. If two tabs show different *entities*, they are navigation, not tabs.

### Breadcrumb
**Form:** the chain of lexicon nouns and record names. `Invoices / Invoice 4021 / Line items`. Never restate the level type.

### Section and card title
**Form:** noun phrase naming what is inside. One to three words.

| Good | Bad |
|---|---|
| Details | Basic information about this invoice |
| Line items | What products are billed? |
| Notes | Anything else? |

If a card holds one field, the card title duplicates the field label. Delete one, usually the card title. The exception is when splitting a long form into cards gives it a shape a user can scan, which is worth the small redundancy.

### Modal, drawer, and panel title
**Form:** for creating, `Add {noun}`. For editing, the record's name, or `Edit {noun}`. For confirming, the action as a question (see System feedback).

### Wizard step label
**Form:** noun naming what the step collects, parallel across steps. `Details`, `Coverage`, `Review`. Not `Step 2: Now tell us about coverage`.

---

## 3. Explanation

Explanation slots are where all the prose you wanted to put in a label actually belongs. They are not a dumping ground: each has a word budget and a required content order.

### Page tooltip / page description
**Form:** one to two declarative sentences answering, in order: what is this a collection of, and what does the system do with it.

> **Archived records.** Documents retained for historical reference. They remain read-only until restored.

Never open with `Here you can`, `This page allows you to`, or `Use this page to`.

**Rule:** add this description when the intended audience cannot tell what the page is for from its title alone. Keep required explanations persistently available; do not hide them behind hover-only behavior.

### Field help text (persistent, below the field)
**Form:** one sentence stating the consequence of the value or the constraint on it.

> **Retry limit.** Maximum attempts before the operation stops.

Use for anything affecting money, deletion, permissions, or downstream systems. The user needs it while typing, not on hover.

### Field tooltip (on an icon, on hover or focus)
**Form:** same content as help text, hidden behind an affordance.

Use when the explanation matters on first encounter and is noise afterward. Must be reachable by keyboard and readable by screen readers; a tooltip that only exists on mouse hover is not an explanation, it is a decoration.

### Section description
**Form:** one sentence, only when the grouping itself is non-obvious. Most sections need none. A description that restates the section title is worse than no description.

---

## 4. Data display

### Table column header
**Form:** noun phrase naming the value in the cell. One to three words. No question words, no sentences.

The header names what is *in the column*, not what the feature *does*.

| Good | Bad | Why |
|---|---|---|
| Retry limit | How retries are handled | Describes the mechanism |
| Reason | Why | Question word |
| Requester | Who asked | Narrates the flow |
| Received at | When we got it | Conversational, first person |
| Status | Is it active? | Question, and the answer is not boolean-shaped |
| Last sign-in | Has the user logged in recently | Sentence, and the value is a date |

Avoid question words as table headers when a noun phrase names the cell value more directly. If a column needs explaining, add accessible help rather than turning the header into a sentence.

Numeric columns are right-aligned; their headers are too. For a sortable header, keep the visible field name in the control's accessible name, such as `Sort by Status` for a `Status` column.

### Cell value, enum, status badge
**Form:** use the canonical display term consistently within the product and locale. Keep stable machine values separate; API responses do not need localized display text.

- Enum display values are lexicon entries. `Active`, `Paused`, `Archived`. Not `Currently active`, not `Turned off`.
- States are adjectives or past participles, never verbs: `Archived`, not `Archive`. `Pending review`, not `Needs to be reviewed`.
- Never render a raw stored value (`PENDING_REVIEW`, `line_item`) to a user.
- Render empty values with the product's chosen null marker, such as `—`. Distinguish `None`, `N/A`, `null`, blank, unavailable, and redacted when they carry different meanings and when revealing the distinction is safe. Supply accessible text when a symbol alone does not convey the meaning.
- Zero renders as `0`, never as `—`. They are different facts.

### Metric and stat card label
**Form:** noun phrase, plus the period or basis in parentheses when the number is time-bound.

| Good | Bad |
|---|---|
| Revenue (last 30 days) | How much you made recently |
| Open tickets | Tickets that still need attention |
| Delivery rate (last 7 days) | We delivered this many |

This slot is the most common legitimate reason to want explanation in a label. Resist. The parenthetical carries the basis; a tooltip carries the definition, especially for any derived metric. Any metric computed from other metrics **must** have a tooltip stating the formula in plain terms.

### Chart labels
- Chart title: noun phrase naming what is plotted, with the period. `Requests by status (last 90 days)`.
- Axis label: the measure and its unit. `Requests`, `Response time (ms)`.
- Legend entry: the lexicon term for the series. Never a sentence, never a re-explanation of the chart.
- Never label a chart with its own chart type. `Revenue by month`, not `Bar chart of revenue`.

### Counts and result summaries
**Form:** `{n} {noun}`, correctly pluralized. `1 invoice`, `12 invoices`.

Never `Showing 12 of 12 results`. Never `You have 12 invoices`. When pagination genuinely needs a range, state it as data: `1–50 of 213`.

### Audit and activity log entries
**Form:** `{subject} {past-tense verb} {object}`, with the actor named and the timestamp separate.

> `An administrator archived Invoice 4021` · `Mar 4, 2026, 2:14 PM EST`

Never `This invoice was archived by someone` and never a first-person system voice.

---

## 5. Input

### Field label
**Form:** use the product's field-label style. A concise noun phrase often fits data-entry fields; a direct question may fit a form journey. Keep format and consequence explanations in hint or help text.

| Good | Bad |
|---|---|
| Reason | Why was this document archived? |
| Requester | Who submitted this request? |
| Retry limit | How many attempts are allowed? |
| Line items | What products are included? |
| Retry limit | How many times should we retry? |

**Trace the label, database column, and API field to the same canonical concept** (see `data-and-contracts.md`). Prefer the canonical term in new work. When compatibility, localization, privacy, computed values, or audience needs require different surface words, document the mapping instead of hiding it in scattered view code.

### Placeholder
**Form:** an example value, or nothing.

A placeholder is not a second label and not help text. It disappears when typing starts, so it must never carry anything the user needs while typing.

| Good | Bad |
|---|---|
| name@example.test | Enter the account email address |
| 5 | How many attempts? |
| (nothing) | Type here |

Never put required-ness, format rules, or constraints in a placeholder. Never use a placeholder in place of a label.

### Choosing the control from the data, not the story
A control that encodes a *narrative* instead of a *value* creates redundant fields and unmaintainable state. This is the schema-level form of failure 1.

| Data shape | Correct control | Wrong control |
|---|---|---|
| Integer with documented bounds and default | Number input with visible min and max | Toggle plus a hidden count field |
| One of three mutually exclusive states | Radio group or select | Two toggles |
| Genuinely two-state boolean | Toggle or checkbox | Select with Yes and No |
| Multi-select from a fixed list | Checkbox list | Free-text chips |
| Fixed list over ~8 items | Searchable select | Long radio group |

If a toggle exists to answer a question that a single value already answers, delete the toggle and expose the value.

### Option label (radio, checkbox, select)
**Form:** the lexicon value, not a sentence about it. Options in a group are grammatically parallel and roughly equal in length.

| Good | Bad |
|---|---|
| Active / Paused / Archived | Currently active / Temporarily paused / No longer used |

Never make one option a sentence and another a word.

### Settings toggle
**Form:** the label names the thing being controlled, stated positively. The on state means the named thing is true.

| Good | Bad | Why |
|---|---|---|
| Email notifications | Enable email notifications | The control already conveys "enable" |
| Two-factor authentication | Turn on 2FA for extra security | Verb plus sales pitch in a label |
| Show completed tasks | Hide completed tasks | Negated labels make the off state ambiguous |

Prefer a positive toggle label when it expresses the same domain fact. "Hide completed, off" is a
puzzle. Preserve regulated wording, a genuinely negative domain fact, or an established platform
label; put consequences in help text rather than silently reversing the stored meaning.

### Numeric input with a range
Show bounds and default where the user can see them without hovering.

> **Retry limit** · 1–10 · defaults to 5

Never rely on validation to teach a constraint the user could have been shown.

### Required and optional
Mark whichever is rarer. If most fields are required, mark only the optional ones with `Optional` after the label. Asterisks require a legend and are worse than the word.

### Search input
**Form:** placeholder names the searchable fields. `Search by name or reference code`. Not `Search...`, not `Find an invoice`.

### Filter label and filter chip
**Form:** `{Field}: {value}`. `Status: Active`. Never `Filtered by status of active`. Active filters are always visible; a filter the user cannot see is the cause of most "my data disappeared" reports.

### Sort control
**Form:** `Sort by {field}` with the field name matching the column header exactly. Direction stated in the field's own terms: `Newest first`, not `Descending`.

---

## 6. Actions

### Primary button
**Form:** verb plus lexicon object, naming the literal thing that happens.

| Good | Bad | Why |
|---|---|---|
| Archive document | Update record | Vague verb hides the actual state change |
| Save invoice | Submit | Does not name the object |
| Add line item | Create new | Does not name the object |
| Send invoice | Confirm | Names the interaction, not the act |

If the button opens a form rather than performing the act, it still names the destination act. `Add invoice` opening a modal is correct; `Open invoice form` is not.

Use `...` after a label only where the platform convention means "opens a dialog needing more input," and only if the product uses that convention consistently.

### Secondary and dismiss
`Cancel` abandons an edit. `Close` dismisses a read-only view. `Back` steps within a flow. Do not invent alternatives.

### Menu item
**Form:** verb plus object, same as a button. Menu section headers are nouns. Never mix verbs and nouns in one menu list.

### Bulk action
**Form:** verb plus count plus pluralized object, with the count live against the selection. `Delete 4 invoices`.

### Destructive action
**Form:** the real verb plus the object. `Delete invoice`, not `Remove`, not `Clear`, not `Are you sure?` The confirm button inside the dialog repeats the same verb and object.

### Disabled control
Explain why a disabled control is unavailable when people are likely to need or expect the action
and disclosure is safe.

> Cannot archive an invoice with active line items.

Explain a disabled control when people are likely to need or expect the action. Hide it when the action is irrelevant or disclosure would be unsafe. If the reason needs substantial explanation, redesign the state instead of forcing it into a tooltip.

### Icon-only control
Requires an accessible name and, when the meaning is not otherwise persistently available, an
accessible tooltip or equivalent explanation. Reuse the same action concept and object as the
equivalent text button. When visible text exists, ensure the accessible name contains it; exact
equality is a strong maintenance default, not the WCAG requirement.

---

## 7. System feedback

### Empty state: never had data
**Form:** factual statement of the state, plus the primary action. No sympathy, no metaphor, no personality.

| Good | Bad |
|---|---|
| No archived documents. | There is nothing here right now |
| No invoices yet. | It's quiet in here! |
| No invoices. | Time to get paid! |

In consumer register, one sentence of guidance may follow the statement. The statement still comes first.

### Empty state: filtered or searched to zero
**A separate slot, and the one most often missed.** Zero rows because nothing exists and zero rows because a filter excluded everything are different states with different remedies. Showing the never-had-data message while a filter is active is a defect, not a wording problem: it makes users believe their data was deleted.

**Form:** state that the filter or query excluded everything, and offer to clear it.

> No invoices match the current filters. **Clear filters**
> No results for "invoce". Check the spelling or clear the search.

**Rule:** any list with filtering or search requires both empty states, selected on `total == 0` versus `filtered == 0 && total > 0`. Build this into the shared list component so it cannot be forgotten per screen.

### Loading
A skeleton or spinner with no text, or `Loading {noun}`. Never `Hang tight`, never `Working on it`, never a rotating set of jokes.

### Validation error, field level
**Form:** name the constraint in the same words as the field. Appears beside the field, not in a global banner.

| Good | Bad |
|---|---|
| Retry limit must be between 1 and 10. | Invalid value |
| Enter a date in MM/DD/YYYY format. | The received at field must be a valid date. |

Two recurring problems:
- **Framework defaults leak the column name.** `The received_at field must be a valid date` exposes the schema. Rewrite every default message in display language.
- **Validating input the interface itself produced.** If a date picker's output fails date validation, the message is not the bug. Fix the format contract between control and validator instead of rewording the error.

### Conflict and uniqueness error
**Form:** name the entity and the condition. Never substitute a pronoun for an entity that has a name.

| Good | Bad |
|---|---|
| An invoice with that number already exists. | Something here already goes by that name |
| That document is already archived. | Already added |

### System error
**Form:** state what failed, state whether data was saved, state what to do, give a reference.

> Could not save the invoice. No changes were made. Try again, or contact support with reference `4f21c8`.

Do not let `Oops`, `Something went wrong`, or an apology replace the data state and recovery path.
For serious harm, a product voice may include a brief apology after those facts; record that choice
in the content style instead of improvising it per error.

### Partial failure (imports, bulk operations)
**Form:** state the split, then how to see the failures.

> Imported 37 of 40 rows. 3 rows failed. **View errors**

Never report a partial failure as a success. Never report it as a total failure.

### Progress
**Form:** `{verb-ing} {n} of {total} {noun}`. `Importing 120 of 4,300 rows`. Percentages alone are less useful than counts when the units mean something.

### Success confirmation and toast
**Form:** past-tense verb plus object. `Invoice saved.` `Document archived.` Never `Success!`, never `All set!`, never an exclamation mark.

Suppress the toast entirely when the result is visible on screen. A row appearing in a table confirms itself. (Some teams prefer an explicit confirmation regardless; if so, record that in the lexicon file and be consistent.)

### Confirmation dialog
- **Title:** the action as a question, using the real verb. Use `{Verb} {name}?` when the record name
  is unique and the surrounding context makes its type clear (`Retire Starter?`). Add the entity type
  when the name alone could be ambiguous (`Retire plan Starter?`). Use `this {entity}` only when no
  useful record name exists (`Delete this invoice?`).
- **Body:** name the record or value, the exact availability change, what happens to existing uses,
  and whether reversal is possible. Use short factual sentences; omit any consequence the product
  behavior does not establish.
- **Confirm button:** repeats the verb and entity type (`Retire plan`, `Delete invoice`). Use the
  instance name only when it materially prevents choosing the wrong record or the product has chosen
  that convention consistently. Never `OK`, never `Yes`.

| Don't | Do |
|---|---|
| `It stops being offered for new work. Everything already pointing at it keeps working, and nothing is deleted. This can be undone.` | `{Name} will no longer be available for new {specific records}. Existing {specific records} will remain unchanged. You can restore {name} from {location}.` |
| `This change is permanent.` | `{Name} will no longer be available. This action cannot be undone.` |
| `Are you sure?` | `Archive {name}?` or `Delete {name}?`, matching the real action |

Do not use `it`, `everything`, `work`, `pointing at`, `permanent`, or `undo` as substitutes for the
actual entity, relationship, consequence, and recovery path. Do not claim an action is reversible
unless a real restore path exists and is available to this user. Do not call it irreversible when
the product can restore it.

Name the recovery actor when restoration is role-gated: `An admin can restore North from Archived
workspaces within 30 days.` Use `within {duration}` for a deadline to act; use `for {duration}` only
when describing how long the system retains or offers something. If the acting user cannot recover
the record, do not write `You can restore`.

Missing facts that could change consent block exact confirmation copy. Before writing the modal,
resolve unknown deletion, existing-use impact, irreversibility, recovery path, and actor permission
when any applies to the action. Do not ship a shorter modal that hides an unresolved material
consequence. Omit only consequences verified to be irrelevant.

Reserve confirmation for destructive, irreversible, high-impact, regulated, or otherwise risky
acts under the product's interaction policy. Reversibility alone does not prove that undo exists or
that confirmation is unnecessary. Prefer undo only when the system genuinely supports a timely,
reliable reversal and the interaction fits the risk.

### Undo affordance
**Form:** the past-tense confirmation plus `Undo`. `Invoice archived. **Undo**`

### Permission message
**Form:** state the requirement, not the denial. `Requires the Billing admin role.` Not `You don't have permission to do that.`

### Banner and system announcement
**Form:** what is happening, when it ends, what the user should do. `Scheduled maintenance from 2:00 to 4:00 AM EST on March 8. Exports will be unavailable.` No apologies, no marketing.

---

## 8. Outside the screen

The same grammar applies wherever the product speaks.

- **Email subject:** noun phrase naming the event and the object. `Invoice 4021 overdue`. Not `Action required!` or `A quick note about your invoice`.
- **Notification title:** subject plus past-tense verb plus object, as with audit entries.
- **Exported file names and headers:** column headers in an export match the on-screen headers exactly. A user reconciling a spreadsheet against a screen should not have to translate.
- **API error messages and codes:** codes are stable, uppercase, and specific (`INVOICE_NUMBER_TAKEN`). Messages follow the conflict-error grammar. Never return an internal exception string to a client.
- **Log lines:** structured, factual, with the entity named. Logs are read by engineers under pressure, which is the fortieth-time test at its most extreme.

---

## 9. Slot quick reference

| Slot | Form | Terminal punctuation |
|---|---|---|
| Collection page title | Plural lexicon noun | None |
| Detail page title | Record name | None |
| Nav item | Same noun as its destination | None |
| Tab | Noun or state naming the subset | None |
| Breadcrumb | Chain of nouns and record names | None |
| Section / card title | Noun phrase, 1–3 words | None |
| Column header | Noun phrase naming the cell value | None |
| Cell value, badge | Lexicon term, adjective or participle | None |
| Metric label | Noun phrase + basis in parentheses | None |
| Field label | Lexicon noun phrase, 1–3 words | None |
| Placeholder | Example value, or nothing | None |
| Option label | The value, parallel across the group | None |
| Settings toggle | The thing controlled, stated positively | None |
| Button | Verb + object | None |
| Menu item | Verb + object | None |
| Page tooltip | 1–2 declarative sentences | Period |
| Field help | 1 sentence: consequence or constraint | Period |
| Empty state | Factual statement of the state | Period |
| Validation error | Constraint in the field's own words | Period |
| Conflict error | Entity + condition | Period |
| System error | What failed, data state, what to do | Period |
| Success toast | Past-tense verb + object | Period |
| Confirmation title | The action as a question | Question mark |
| Confirm button | Repeats the verb + object | None |
| Audit entry | Subject + past-tense verb + object | None |
| Disabled tooltip | The condition that would enable it | Period |
