# Name code identifiers

Dos and don'ts for identifiers in source code. Read alongside `data-and-contracts.md` when the name also exists in the database or an API contract, which it usually does.

The governing rule from `SKILL.md` applies here as much as on screen: name values and entities for what they represent, and operations for the outcome they produce rather than their mechanism.

## Variables

**Form:** noun or noun phrase naming the value. Length proportional to scope: a loop index can be `i`; a module-level value cannot.

| Don't | Do |
|---|---|
| `data`, `info`, `result`, `obj`, `tmp`, `val` | `invoices`, `rateSheet`, `normalizedAddress` |
| `d`, `cr`, `prdLn` | `duration`, `invoice`, `lineItem` |
| `userList`, `invoiceArray`, `strName` | `users`, `invoices`, `name` |
| `data2`, `invoices_new`, `finalFinalTotal` | Distinct meanings get distinct names |
| `timeout`, `size`, `price` (units unstated) | `timeoutMs`, `sizeBytes`, `priceCents` |
| `flag`, `check`, `status2` | `isArchived`, `hasConsent`, `reviewStatus` |

**Name ambiguous units and currency.** Any value whose unit could be misread carries it: `timeoutMs`, `distanceMeters`, `amountCents`. Follow the product's money representation; when it stores minor units as integers, name that fact, such as `priceCents`.

**Don't** restate the enclosing context: inside a `Invoice` class, the field is `name`, not `invoiceName`. Across the boundary, in a function taking many objects, `invoiceName` is correct. Name for the reader at that point in the code.

---

## Booleans

**Recommended form:** use the language and repository's predicate convention. In languages that use word prefixes, `is` / `has` / `can` / `should` stated positively is a useful default.

| Don't | Do | Why |
|---|---|---|
| `active` | `isActive` | Reads ambiguously as a noun |
| `is_not_active`, `disabled`, `hideCompleted` | `isActive`, `showCompleted` | Negation produces `!isNotActive` at call sites |
| `flag`, `check`, `status` (holding a bool) | `hasConsent`, `isArchived` | Names nothing |
| `deleted` | `isDeleted` or `deletedAt` timestamp | If you need to know *when*, it was never a boolean |
| `userType` (holding true/false) | `isInternal`, or an enum | A boolean pretending to be a category |

**Don't make one boolean carry a third meaning.** When a configured value can be enabled, disabled,
or inherited, model and name the configured value separately from the effective computed condition.
Use an enum when those meanings are mutually exclusive. Keep separate fields when the facts are
orthogonal and can be true together; do not force a fraud hold and a billing pause into one enum
merely because both affect availability.

**Don't** name a boolean after the question it answers (`did_the_user_confirm`). Name it after the condition it asserts (`isConfirmed`).

---

## Collections

**Form:** plural of the element noun. `invoices`, `lineItems`.

| Don't | Do |
|---|---|
| `invoiceList`, `invoiceArray`, `invoiceCollection` | `invoices` |
| `invoiceMap` | `invoicesById`, `ratesByLineItem` |
| `items`, `records`, `rows`, `entries` | The element's actual noun |
| `invoicesData` | `invoices` |

**Do** name a map by its key and value: `invoicesById` reads correctly at the call site (`invoicesById[id]`). `invoiceMap` does not.

**Do** name a count `invoiceCount` or `totalInvoices`, never `invoices` doing double duty.

---

## Functions and methods

**Form:** verb plus object. The verb states the *effect class*; the object states what it acts on.

| Don't | Do | Why |
|---|---|---|
| `processData()`, `handleThing()`, `doWork()` | `normalizeAddress()`, `archiveInvoice()` | Names the fact that code runs, not what it accomplishes |
| `manageInvoices()` | Split into the actual operations | "Manage" means the function does several things |
| `getInvoicesAndSendEmails()` | Two functions | `and` in a name is the function admitting it does two jobs |
| `check(user)` | `isEligible(user)` or `assertEligible(user)` | "Check" hides whether it returns, throws, or mutates |
| `getTotal()` that recalculates and writes to the DB | `recalculateTotal()` | A `get` that has side effects is a trap |
| `data()` | `rateSheet()` | Grab-bag |

**Do** make predicates read as an assertion at the call site: `if (invoice.isEligible())`, not `if (invoice.eligibility())`.

**Do** name a function for its outcome, not its implementation. `fetchInvoicesFromRedisThenFallbackToPostgres()` is a comment wearing a function's clothes. `getInvoices()` is the name; the caching strategy is an implementation detail that will change.

**Don't** let a name outlive its behavior. See [Name drift](#name-drift).

---

## Verb vocabulary

Use the project's documented verb semantics. If none exist, start with the defaults below. The don't here is not any individual verb; it is using several synonyms for one operation without a real distinction.

| Verb | Means |
|---|---|
| `get` | Returns something already in memory or trivially derived. No I/O, no side effects. |
| `fetch` / `load` | Performs I/O. May fail, may be slow. |
| `find` | May return nothing. Returns null or an empty result rather than throwing. |
| `require` / `getOrFail` | Returns or throws. Never returns null. |
| `list` / `search` | Returns a collection, possibly filtered or paginated. |
| `build` / `create` | Constructs a new value in memory. |
| `save` / `store` / `persist` | Writes. Prefer one primary verb within a bounded API; preserve established public names until a compatible migration is planned. |
| `compute` / `calculate` | Pure derivation from inputs. |
| `ensure` | Use only when the operation's contract is idempotent: it makes a condition true and is safe to call twice. It does not imply exactly-once delivery. |
| `validate` | Returns errors. |
| `assert` | Throws on failure. |
| `to` / `as` | Converts. `toCents()`, `asJson()`. |
| `on` / `handle` | Reacts to a named event. Only valid when bound to a specific event: `onInvoiceArchived`, never `handleData`. |

Record the chosen set in the lexicon file. The specific choices matter far less than the fact that there is one.

---

## Classes and types

**Form:** singular noun naming the responsibility.

| Don't | Do | Why |
|---|---|---|
| `InvoiceHelper`, `InvoiceUtils`, `InvoiceManager` | `InvoiceRateSheet`, `InvoiceArchiver`, `InvoiceRepository` | These suffixes mean "assorted functions about invoices." They accumulate until nobody can describe the class. |
| `InvoiceData`, `InvoiceInfo`, `InvoiceObject` | `Invoice` | The suffix adds nothing |
| `Processor`, `Handler`, `Engine`, `Service` used generically | The specific role | `Service` is acceptable as a codebase-wide layer convention, not as a shrug |
| `IManager`, `AbstractBaseInvoiceFactoryImpl` | Name the thing | Ceremony is not meaning |

**Do** use `-er` names where the class genuinely is an actor with one job: `AddressNormalizer`, `InvoiceRenderer`. The test is whether you can state the responsibility in one sentence without "and."

**Do** name DTOs and view models after their purpose and shape: `InvoiceListItem`, `InvoiceCreateRequest`. Not `InvoiceDto2`.

For ORM models and relationships, preserve the framework's derivation rules. A model name usually
names one entity; relationship accessors reflect cardinality (`invoice` for one, `invoices` for
many) in the language's convention. If a role-bearing relationship such as `approvedBy` no longer
matches the inferred foreign key, configure that mapping explicitly rather than distorting the
domain name to recover convention magic.

---

## Modules and files

**Form:** matches the primary export, in the codebase's file convention.

| Don't | Do |
|---|---|
| `utils.ts`, `helpers.php`, `common.py`, `misc.js` | Name by domain: `formatting.ts`, `dates.ts` |
| `index.ts` holding logic | `index` re-exports; logic lives in named files |
| `InvoiceController.php` containing line-item logic | Keep the file's contents matching its name |

Treat a growing `utils` file as a signal to find the concepts inside it. When the ecosystem or
repository intentionally uses a shared utility module, preserve that convention and improve names
within its boundary rather than creating churn for the label alone. If a helper serves several
domains, prefer what it does (`retry.ts`, `pagination.ts`) over the fact that it is a helper.

---

## Parameters

**Form:** name the role in this function, not the type.

| Don't | Do |
|---|---|
| `func(str, num, bool)` | `func(name, retryLimit, isActive)` |
| `save(invoice, true, false)` | `save(invoice, { validate: true, notify: false })` |
| `copy(a, b)` | `copy(source, destination)` |

**Avoid ambiguous bare booleans.** When `save(invoice, true)` does not explain the condition at the call site, use named options, an enum, or two functions.

**Do** order parameters consistently across the codebase: subject first, options last.

---

## Constants and magic values

**Form:** name the meaning, never the literal.

| Don't | Do |
|---|---|
| `THREE = 3` | `DEFAULT_RETRY_LIMIT = 5` |
| `if (status === 2)` | `if (status === InvoiceStatus.Archived)` |
| `TIMEOUT = 30` | `REQUEST_TIMEOUT_SECONDS = 30` |
| `if (role === 'admin')` scattered in 40 files | One `Role` enum, referenced everywhere |

**Do** put the value's business justification in a comment when it is non-obvious: a retry limit chosen to fit inside a partner's rate window deserves one line saying so.

---

## Enums in code

**Form:** the type is a singular noun; the members are **states, expressed as adjectives or past participles**, never verbs.

| Don't | Do |
|---|---|
| `Status.Archive`, `Status.Suspend` | `Status.Archived`, `Status.Suspended` |
| `Status.OK`, `Status.STATUS_2` | `Status.Active`, `Status.PendingReview` |
| Raw strings compared across the codebase | The enum, one definition |

**Do** keep exactly one mapping from stored value to display term, in one place. Never re-derive a display string from a stored value in a view. See `data-and-contracts.md` and `product-ui.md`.

---

## Errors and exceptions

**Form:** `{Subject}{Condition}Error`. The type names the failure; the message follows error grammar.

| Don't | Do |
|---|---|
| `Error`, `AppError`, `CustomException` | `InvoiceNameTakenError`, `RateSheetExpiredError` |
| `throw new Error('failed')` | A typed error carrying the entity and condition |
| Messages with pronouns: `it already exists` | `An invoice with that name already exists.` |
| Leaking internals: `SQLSTATE[23000] duplicate key` | Map to a domain error at the boundary |

**Do** share one domain error classification while writing details for the audience: a user needs recovery, a log needs safe diagnostics, and an API client needs a stable code. See `product-ui.md` and `data-and-contracts.md`.

---

## Events, commands, jobs

Distinguish facts that occurred, actions requested, and the workers that perform them. Use the project's event-naming convention; the forms below are a practical default.

| Kind | Form | Example |
|---|---|---|
| **Event** (something happened, past) | `{entity}.{past-tense verb}` | `invoice.archived`, `invoice.paid` |
| **Command** (do this, imperative) | `{Verb}{Object}` | `ArchiveInvoice`, `SendInvoice` |
| **Job / worker** (the runner) | `{Verb}{Object}Job` | `SendInvoiceJob` |
| **Handler** (reacts to an event) | `on{Event}` or `handle{Event}` | `onInvoiceArchived` |

| Don't | Do |
|---|---|
| `invoiceUpdate`, `InvoiceEvent`, `invoice.change` | `invoice.archived`, `invoice.rates_updated` |
| An event named as a command (`invoice.archive`) | Events are past tense. If it has not happened yet, it is a command. |
| `ProcessQueueJob` | Name the work: `ReconcileInvoiceRatesJob` |

**Do** name events for the business fact, not the table write. `invoice.paid` survives a schema change; `invoices_row_updated` does not.

Keep delivery guarantees out of names unless the contract proves them. Retries keep the same command
name; duplicate delivery keeps the same event name. Put attempt, event, and deduplication identifiers
in the documented contract or structured fields, and define what `completed` means before using it
in a log or operation name.

---

## Feature flags

**Form:** positive, named for what it enables, with an owner and a removal date recorded where flags are defined.

| Don't | Do |
|---|---|
| `new_ui`, `flag_2`, `temp_fix` | `invoice_split_form`, `archive_bulk_import` |
| `disable_old_checkout` | `checkout_v2` |
| Flags with no expiry | Every flag has an owner and a date; expired flags are removed, not left on |

A flag left in the codebase after rollout is a permanent extra branch in every reader's mental model.

---

## Config keys and environment variables

**Common environment-variable form:** `SCREAMING_SNAKE_CASE`, namespaced by subsystem, with ambiguous units suffixed. Follow the runtime's established convention.

| Don't | Do |
|---|---|
| `TIMEOUT` | `PAYMENTS_API_TIMEOUT_SECONDS` |
| `KEY`, `TOKEN`, `URL` | `STRIPE_SECRET_KEY`, `REDIS_URL` |
| `DEBUG_MODE_2` | `LOG_LEVEL` |
| Booleans as `"1"` / `"yes"` / `"on"` inconsistently | One convention, documented |

**Do** name the environment in the value, not the key. `DATABASE_URL` in each environment; never `PROD_DATABASE_URL` referenced from application code.

---

## Tests

**Form:** name the behavior and the condition, not the method under test.

| Don't | Do |
|---|---|
| `testInvoice()`, `test1()`, `itWorks()` | `archivingInvoiceRemovesItsLineItems()` |
| `testSaveMethod()` | `savingInvoiceWithDuplicateNameReturnsConflict()` |
| `testEdgeCase()` | Name the edge case |

**Do** make the test name readable as a sentence in the failure output. The person reading it is debugging at speed and should not have to open the file to learn what broke.

---

## Comments and docstrings

The rule is **why, not what.** Code states what it does; comments explain context or constraints that the code cannot express clearly.

| Don't | Do |
|---|---|
| `// increment the counter` above `counter++` | Nothing |
| Narrating the algorithm in prose | Name the function well and delete the narration |
| `// process the request` above a multi-stage workflow | State the stages, ordering constraint, and boundary that a future maintainer must preserve |
| Em dashes, rhetorical questions, jokes | Plain declarative sentences |
| Commented-out code left in place | Delete it; version control remembers |
| `// TODO: fix this` | `// Remove after the address migration completes; tracked in the migration plan.` |

**Do** comment: non-obvious business rules, the reason a constant has its value, deliberate deviations from a convention, known limitations, and anything a future reader would otherwise "fix" by breaking it.

**Explain non-obvious flow at the level where the flow is owned.** A module, orchestration function,
state machine, or boundary adapter may need a short comment that names:

1. the stages and why their order matters;
2. the state or invariant each stage hands to the next;
3. the external side effect, retry, transaction, or compatibility boundary; and
4. where the authoritative contract or longer design explanation lives.

Write for the future developer or agent deciding whether a step can be moved, removed, retried, or
renamed. Keep the comment next to the owning abstraction and update it with the behavior. Do not
duplicate every implementation step; that creates a second program in prose that drifts from the
code.

Comment only facts established by the code, contract, or supplied requirements. Do not invent
precedence, transaction timing, retry behavior, side effects, or invariants to make an example feel
complete. When the flow is not known, use a structural placeholder such as `{why order matters}` in
draft guidance or state that no factual comment can be written yet.

```ts
// Validate before reserving inventory: reservation emits a partner-visible event and must not run
// for requests that will be rejected. Payment capture happens after the transaction commits so a
// database rollback cannot leave a captured payment without an order.
```

**Docstrings** state the contract: what it returns, what it throws, what it mutates, what units it expects. Not a paraphrase of the signature.

---

## Commits, branches, pull requests

**Commit subject:** imperative verb plus object, naming the entity. Under ~70 characters, no trailing period.

| Don't | Do |
|---|---|
| `fix`, `updates`, `wip`, `changes per feedback` | `Rename why column to reason on archived_records` |
| `Fixed the thing that was broken` | `Fix empty state shown when invoice filters are cleared` |
| Past tense mixed with imperative | One tense, repo-wide (imperative is the common default) |

**Commit body:** why the change was needed and what it affects. The subject says what changed; the body says why, which is the part unavailable from the diff.

**Branch:** follow the repository's branch convention. Use a short descriptive slug, such as `fix/archive-copy`; include a ticket only when the repository requires one.

**Pull request title:** follow the repository's title convention; otherwise use the same imperative grammar as a commit subject. State the user-visible effect before implementation detail.

---

## Name drift

The most common naming defect in a mature codebase is not a bad original name. It is a **name that was right and stopped being right.**

| Situation | Action |
|---|---|
| A function's behavior changed | Rename it in the same commit |
| A column now stores something broader than its name | Inventory every boundary, then stage a compatibility-safe rename across the column, field, label, and lexicon entry |
| A flag outlived its rollout | Remove the flag and the branch |
| A term was renamed on screen only | Decide whether it is display-only or domain-wide; document the mapping or stage propagation across affected boundaries |

**Do not replace uncertainty with false precision.** `data` tells a reader nothing; `invoiceEmail`
holding a phone number tells them something false. Resolve the meaning when evidence is available;
when it is not, state the uncertainty instead of inventing a precise domain name.
**Do** inventory every layer a rename may cross: the column, migration, model attribute, API field, validation rule, form field, label, export header, saved filters or reports, and lexicon. Change private names atomically; stage stored and published contracts through their compatibility process. Document intentional differences so they do not become accidental drift.
