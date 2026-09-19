# Maintain the product lexicon

The conventions in this skill are defaults; each product's vocabulary is specific to its domain. Keep a lexicon when terms recur across teams or layers, and look terms up before coining synonyms.

This is the load-bearing artifact. Consistency is unreachable through better writing, because every file and screen written independently invents a fresh synonym for the same idea. Consistency is only reachable through lookup.

Keep it high level. Record recurring domain concepts, product-wide conventions, cross-layer forms,
and intentional exceptions. Do not inventory every field label, one-off string, local variable, or
schema column. A large product may have thousands of those; they should derive from the lexicon and
their local model rather than be duplicated into it.

## Where it lives

Keep the lexicon in a repository location documented for contributors and agents, such as `docs/lexicon.md` or beside the schema.

## Rules

- When a recurring concept is missing, confirm the term from product evidence or an appropriate owner, then update the lexicon with the naming change.
- One entry per concept, not per layer. The entry carries every layer's form of the term.
- Add an entry when a concept recurs across teams, features, or boundaries, or when ambiguity has a
  material cost. Ordinary fields that already follow an established concept and slot convention do
  not need their own entry.
- The **avoid list matters alongside the canonical term.** It makes known synonym drift reviewable while allowing contextual uses that carry another meaning.
- Put a word on an avoid list only for the named concept. The same word may be canonical for a
  distinct concept, such as `suspended` for an involuntary hold and `paused` for a voluntary break.
- Shared, product-significant enum display values are lexicon entries. Local implementation enums
  that already derive unambiguously from a canonical concept remain with their owning model.
- Record fixed vendor, generated, regulated, localized, privacy-specific, and published legacy forms
  as mappings rather than treating them as drift or precedent for new first-party names.
- Keep one model's explicit table, primary key, relationship key, cast, or other ORM configuration
  beside that model. Promote it to the project lexicon only when the exception recurs across teams or
  boundaries, changes the product vocabulary, or is needed to prevent a material ambiguity.
- When a term is renamed, update the lexicon with the implementation when feasible. For a staged migration, record current, target, and compatibility forms.
- Requirements documents are not the lexicon. PRD prose describes mechanisms; the lexicon names values.

---

## Template

```markdown
# Lexicon

## Product decisions

Register:            operator
Case (UI):           sentence case everywhere
Case (columns):      snake_case
Case (API):          snake_case
Case (code):         camelCase identifiers, PascalCase types
Enum storage:        snake_case
Framework / ORM:     Laravel defaults, with explicit exceptions recorded at the owning model
Dates shown as:      Mar 4, 2026, 2:14 PM EST
Currency:            integer minor units, column suffix _cents
Null renders as:     —
Absence states:      unknown / not applicable / withheld / redacted (product-defined display terms)
Acronym casing:      repository or language convention; external forms mapped at the boundary
Toasts:              archived when the result is visible on screen
Confirmation button: verb + entity type (record name only when product convention requires it)
Persist verb:        save   (not store, not persist)
Read verbs:          get (in-memory) / fetch (I/O) / find (may be empty)

## Terms

### Invoice
display:     Invoice
plural:      Invoices
column:      invoice_id
api:         invoice
code:        Invoice, invoice
definition:  A request for payment issued to an account.
avoid:       bill, charge, payment request, "something here"

### Retry limit
display:     Retry limit
column:      retry_limit  (integer; bounds and default belong in the contract)
api:         retry_limit
code:        retryLimit
definition:  Maximum attempts before an operation stops.
avoid:       retries setting, attempt mode, "how retries are handled"

### Reason
display:     Reason
column:      reason  (text)
api:         reason
code:        reason
definition:  Why a document was archived.
avoid:       why, note, explanation, cause

## Enums

### Document status
stored       display        meaning
active       Active         Available for normal work.
paused       Paused         Temporarily unavailable. Configuration retained.
archived     Archived       No longer in active use. Retained for history.
avoid:       inactive, disabled, off, deleted, "turned off"
```

---

## Building the first lexicon for an existing product

1. **Inventory the nouns.** List every table, every top-level API resource, and every page title. That is most of the domain.
2. **Find the collisions.** Grep for the obvious synonym clusters (`user` / `customer` / `client`, `delete` / `remove` / `archive`). Each cluster is one concept wearing several names, or two concepts sharing one. Both need deciding.
3. **Ask practitioners and check the contracts.** Prefer the term people in the domain use consistently while checking user comprehension, accessibility, legal wording, and published compatibility. A legacy schema name does not decide the vocabulary by itself.
4. **Separate overlapping from exclusive states.** Use one enum only when states are mutually
   exclusive. Record separate concepts when they can coexist, including configured versus effective
   values.
5. **Record discouraged alternatives.** Build the avoid list from the synonym drift found in step 2 and state intentional exceptions.
6. **Decide the product-level settings** at the top of the file once, so they are not re-litigated per screen.
7. **Do not mass-rename without a migration plan.** Record current, target, and compatibility forms; then make bounded, compatibility-safe changes. An undocumented partial rename adds another vocabulary state.

## Maintain the lexicon

- Any pull request introducing a recurring or product-significant domain concept updates the lexicon
  in the same change. A one-off implementation field does not.
- Any rename updates the lexicon in the same change as the migration.
- Periodically search code and interface strings for entries on the avoid lists. Classify every hit as drift, an intentional distinct meaning, or a lexicon entry to revise.
